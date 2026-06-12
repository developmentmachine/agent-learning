/**
 * 向量数据库完整入门示例（TypeScript + Qdrant + 本地 Embedding 模型）
 *
 * 与 Python 版 vector_db_demo.py 对齐的同一条链路：
 *   原始文本 → Embedding 向量化 → 写入 Qdrant → 混合检索 → 组装 RAG Context
 *
 * 前置条件：
 *   1. Node.js 18+
 *   2. Qdrant 服务（JS SDK 无内存模式，必须先起服务）:
 *        docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
 *
 * 运行：
 *   npm install
 *   npm start
 *
 * 可选环境变量：
 *   QDRANT_URL=http://127.0.0.1:6333   # 默认即此地址
 */

import { QdrantClient } from "@qdrant/js-client-rest";
import { pipeline, type FeatureExtractionPipeline } from "@xenova/transformers";

// =============================================================================
// 类型与配置
// =============================================================================

/** 单篇样例文档的结构 */
interface Article {
  id: number;
  category: string;
  title: string;
  content: string;
  views: number;
}

/** Qdrant search 返回的单条命中（简化类型，够 demo 用） */
interface SearchHit {
  id: number | string;
  score: number;
  payload?: Record<string, unknown>;
}

// 与 Python 版使用同一 HuggingFace 模型族（384 维）
const EMBEDDING_MODEL_NAME = "Xenova/all-MiniLM-L6-v2";

const COLLECTION_NAME = "article_knowledge_base";

const QDRANT_URL = process.env.QDRANT_URL ?? "http://127.0.0.1:6333";

// 与 Python 版保持相同样例数据，方便你对照两种语言的输出
const SAMPLE_ARTICLES: Article[] = [
  {
    id: 1,
    category: "tech",
    title: "Docker Containerization",
    content:
      "Docker packages applications and dependencies into portable containers, " +
      "making dev/prod environments consistent and deployments repeatable.",
    views: 1200,
  },
  {
    id: 2,
    category: "tech",
    title: "Python Performance Tuning",
    content:
      "Profile hot paths first, prefer vectorized libraries, and avoid " +
      "premature micro-optimizations before measuring real bottlenecks.",
    views: 850,
  },
  {
    id: 3,
    category: "finance",
    title: "Quantitative Trading Basics",
    content:
      "Quant trading uses statistical models and historical data to generate " +
      "signals, with strict risk controls on position sizing and drawdown.",
    views: 3100,
  },
  {
    id: 4,
    category: "tech",
    title: "Kubernetes Pod Networking",
    content:
      "Pods get cluster-internal IPs; Services provide stable endpoints; " +
      "CNI plugins implement overlay or routing between nodes.",
    views: 2100,
  },
];

const USER_QUERY = "How do I speed up Python code and find bottlenecks?";

// =============================================================================
// Embedding：@xenova/transformers 是浏览器/Node 端的 Transformers 运行时
// 角色上对应 Python 的 sentence-transformers
// =============================================================================

let embedder: FeatureExtractionPipeline | null = null;

/**
 * 懒加载 Embedding 模型。
 * 首次调用会下载模型到本地缓存（~/.cache/huggingface），与 Python 版行为类似。
 */
async function getEmbedder(): Promise<FeatureExtractionPipeline> {
  if (!embedder) {
    console.log(`[Embedding] 加载模型: ${EMBEDDING_MODEL_NAME}`);
    embedder = await pipeline("feature-extraction", EMBEDDING_MODEL_NAME);
    console.log("[Embedding] 模型就绪");
  }
  return embedder;
}

/**
 * 把单段文本编码为浮点向量。
 *
 * pooling: 'mean'  → 对 token 向量做平均池化，得到句向量
 * normalize: true → L2 归一化，配合 Qdrant Cosine 距离更稳定
 */
async function embedText(text: string): Promise<number[]> {
  const model = await getEmbedder();
  const output = await model(text, { pooling: "mean", normalize: true });
  // output.data 是 Float32Array；展开为普通 number[] 供 Qdrant 使用
  return Array.from(output.data as Float32Array);
}

async function embedTexts(texts: string[]): Promise<number[][]> {
  const vectors: number[][] = [];
  for (const text of texts) {
    vectors.push(await embedText(text));
  }
  return vectors;
}

function buildTextForEmbedding(article: Article): string {
  return `${article.title}. ${article.content}`;
}

// =============================================================================
// Qdrant 客户端与集合管理
// =============================================================================

function createQdrantClient(): QdrantClient {
  console.log(`[Qdrant] 连接: ${QDRANT_URL}`);
  console.log(
    "[Qdrant] 提示: JS SDK 需要真实服务。若未启动，请运行:\n" +
      "  docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant",
  );
  return new QdrantClient({ url: QDRANT_URL });
}

/**
 * 创建或重建集合。
 * vectorSize 必须等于 Embedding 模型输出维度（all-MiniLM-L6-v2 → 384）。
 */
async function recreateCollection(
  client: QdrantClient,
  vectorSize: number,
): Promise<void> {
  const exists = await client.collectionExists(COLLECTION_NAME);
  if (exists) {
    await client.deleteCollection(COLLECTION_NAME);
  }

  await client.createCollection(COLLECTION_NAME, {
    vectors: {
      size: vectorSize,
      distance: "Cosine",
    },
  });

  console.log(
    `[Qdrant] 已创建集合 '${COLLECTION_NAME}'，向量维度=${vectorSize}，距离=Cosine`,
  );
}

/**
 * 批量 upsert Point。
 * wait: true 表示等待写入完成后再返回（演示用；生产高吞吐可批量异步写）。
 */
async function upsertArticles(
  client: QdrantClient,
  articles: Article[],
  vectors: number[][],
): Promise<void> {
  const points = articles.map((article, index) => ({
    id: article.id,
    vector: vectors[index],
    payload: {
      category: article.category,
      title: article.title,
      content: article.content,
      views: article.views,
    },
  }));

  await client.upsert(COLLECTION_NAME, { wait: true, points });
  console.log(`[Qdrant] 已写入 ${points.length} 条文档`);
}

// =============================================================================
// 检索：纯向量 vs 混合（向量 + payload 过滤）
// =============================================================================

async function hybridSearch(
  client: QdrantClient,
  queryVector: number[],
  options: { category: string; limit: number },
): Promise<SearchHit[]> {
  const hits = await client.search(COLLECTION_NAME, {
    vector: queryVector,
    // filter 是 Qdrant 的 JSON DSL；must 表示 AND 条件
    filter: {
      must: [
        {
          key: "category",
          match: { value: options.category },
        },
      ],
    },
    limit: options.limit,
  });

  return hits as SearchHit[];
}

function printHits(hits: SearchHit[], title: string): void {
  console.log(`\n--- ${title} ---`);
  if (hits.length === 0) {
    console.log("（无结果）");
    return;
  }
  hits.forEach((hit, index) => {
    const payload = hit.payload ?? {};
    console.log(
      `#${index + 1}  id=${hit.id}  score=${hit.score.toFixed(4)}  ` +
        `title=${payload.title}  views=${payload.views}`,
    );
  });
}

function buildRagContext(hits: SearchHit[]): string {
  return hits
    .map((hit) => {
      const payload = hit.payload ?? {};
      return (
        `[doc id=${hit.id} score=${hit.score.toFixed(3)}]\n` +
        `Title: ${payload.title}\n` +
        `Content: ${payload.content}`
      );
    })
    .join("\n\n");
}

// =============================================================================
// 主流程
// =============================================================================

async function main(): Promise<void> {
  console.log("=".repeat(60));
  console.log("向量数据库完整示例：Embedding → Qdrant → 混合检索 → RAG Context");
  console.log("=".repeat(60));

  // 1) 先探活 Qdrant，失败时给出明确指引（比一长串 fetch 报错友好）
  const client = createQdrantClient();
  try {
    await client.getCollections();
  } catch (error) {
    console.error("\n[Qdrant] 无法连接服务。请先启动 Qdrant Docker 容器。");
    console.error(error);
    process.exit(1);
  }

  // 2) 用一条样例文本推断向量维度，避免硬编码 384
  const probeVector = await embedText(buildTextForEmbedding(SAMPLE_ARTICLES[0]));
  const vectorSize = probeVector.length;
  console.log(`[Embedding] 输出维度: ${vectorSize}`);

  // 3) 建集合 + 入库
  await recreateCollection(client, vectorSize);

  const texts = SAMPLE_ARTICLES.map(buildTextForEmbedding);
  const docVectors = await embedTexts(texts);
  await upsertArticles(client, SAMPLE_ARTICLES, docVectors);

  // 4) 用户问题向量化
  console.log(`\n[Query] 用户问题: ${JSON.stringify(USER_QUERY)}`);
  const queryVector = await embedText(USER_QUERY);

  // 4a) 纯向量检索
  const pureVectorHits = (await client.search(COLLECTION_NAME, {
    vector: queryVector,
    limit: 2,
  })) as SearchHit[];
  printHits(pureVectorHits, "纯向量检索 Top-2（无 category 过滤）");

  // 4b) 混合检索：category = tech
  const hybridHits = await hybridSearch(client, queryVector, {
    category: "tech",
    limit: 2,
  });
  printHits(hybridHits, '混合检索 Top-2（category 必须为 "tech"）');

  // 5) RAG Context
  const ragContext = buildRagContext(hybridHits);
  console.log("\n--- 将注入 LLM 的 RAG Context（节选）---");
  console.log(ragContext);

  console.log("\n[Done] 流程结束。");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
