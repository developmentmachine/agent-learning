#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "qdrant-client>=1.12.0",
#     "sentence-transformers>=3.0.0",
# ]
# ///
"""
向量数据库完整入门示例（Python + Qdrant + 本地 Embedding 模型）

演示一条真实 RAG 检索链路：
  原始文本 → Embedding 模型向量化 → 写入 Qdrant → 混合检索（语义 + 元数据过滤）

运行方式（任选其一）：
  chmod +x vector_db_demo.py && ./vector_db_demo.py
  uv run vector_db_demo.py

可选环境变量：
  QDRANT_URL=http://localhost:6333   # 连接本地 Docker 中的 Qdrant；不设则使用内存模式
"""

from __future__ import annotations

import os
import sys
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

# =============================================================================
# 配置区：集中放常量，方便你改模型、集合名、样例数据
# =============================================================================

# 轻量英文嵌入模型（384 维）。首次运行会自动下载到 ~/.cache/huggingface。
# 中文场景可换成 "BAAI/bge-small-zh-v1.5"（512 维），记得同步改 distance 与 collection 重建。
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Qdrant 集合名，可理解为「一张专门存向量的表」
COLLECTION_NAME = "article_knowledge_base"

# 样例知识库：每条记录包含业务元数据 + 用于检索的正文
# 真实项目里正文通常来自 Markdown、网页、数据库字段等
SAMPLE_ARTICLES: list[dict[str, Any]] = [
    {
        "id": 1,
        "category": "tech",
        "title": "Docker Containerization",
        "content": (
            "Docker packages applications and dependencies into portable containers, "
            "making dev/prod environments consistent and deployments repeatable."
        ),
        "views": 1200,
    },
    {
        "id": 2,
        "category": "tech",
        "title": "Python Performance Tuning",
        "content": (
            "Profile hot paths first, prefer vectorized libraries, and avoid "
            "premature micro-optimizations before measuring real bottlenecks."
        ),
        "views": 850,
    },
    {
        "id": 3,
        "category": "finance",
        "title": "Quantitative Trading Basics",
        "content": (
            "Quant trading uses statistical models and historical data to generate "
            "signals, with strict risk controls on position sizing and drawdown."
        ),
        "views": 3100,
    },
    {
        "id": 4,
        "category": "tech",
        "title": "Kubernetes Pod Networking",
        "content": (
            "Pods get cluster-internal IPs; Services provide stable endpoints; "
            "CNI plugins implement overlay or routing between nodes."
        ),
        "views": 2100,
    },
]

# 模拟用户提问。RAG 里会把「问题」向量化，再去库里找最相近的文档片段
USER_QUERY = "How do I speed up Python code and find bottlenecks?"


def create_qdrant_client() -> QdrantClient:
    """
    创建 Qdrant 客户端。

    - 未设置 QDRANT_URL：使用 :memory:，零依赖、适合学习（进程结束数据消失）
    - 设置 QDRANT_URL：连接持久化服务，例如 Docker:
        docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
    """
    url = os.environ.get("QDRANT_URL")
    if url:
        print(f"[Qdrant] 连接远程/本地服务: {url}")
        return QdrantClient(url=url)
    print("[Qdrant] 使用内存模式 :memory:（学习用；生产请起 Docker 并设置 QDRANT_URL）")
    return QdrantClient(":memory:")


def build_text_for_embedding(article: dict[str, Any]) -> str:
    """
    决定「哪段文本」拿去向量化。

    常见策略：
    - 只 embed 标题（快，但语义少）
    - embed 标题 + 正文（更准，RAG 常用）
    - embed 切块后的 chunk（长文档必做）
    """
    return f"{article['title']}. {article['content']}"


def embed_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    """
    调用 Embedding 模型，把字符串列表变成浮点向量列表。

    normalize_embeddings=True 时向量会做 L2 归一化，
    与 Distance.COSINE 搭配时数值更稳定（余弦相似度 ≈ 点积）。
    """
    vectors = model.encode(texts, normalize_embeddings=True)
    # model.encode 返回 numpy.ndarray；Qdrant 需要普通 Python list[float]
    return [vector.tolist() for vector in vectors]


def recreate_collection(client: QdrantClient, vector_size: int) -> None:
    """
    创建（或重建）集合。

    向量库必须先声明：
    - size：向量维度，必须与 Embedding 模型输出一致
    - distance：相似度度量；COSINE 适合大多数语义检索场景
    """
    # 演示脚本每次从头跑，若集合已存在则先删掉，避免维度/配置不一致
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    print(f"[Qdrant] 已创建集合 {COLLECTION_NAME!r}，向量维度={vector_size}，距离=COSINE")


def upsert_articles(
    client: QdrantClient,
    articles: list[dict[str, Any]],
    vectors: list[list[float]],
) -> None:
    """
    批量写入 Point（向量库中的一行记录）。

    每个 Point 三部分：
    - id：主键（整数或 UUID）
    - vector：Embedding 向量（用于相似度检索）
    - payload：业务 JSON 元数据（用于过滤、展示，不参与向量距离计算）
    """
    points = [
        PointStruct(
            id=article["id"],
            vector=vector,
            payload={
                "category": article["category"],
                "title": article["title"],
                "content": article["content"],
                "views": article["views"],
            },
        )
        for article, vector in zip(articles, vectors, strict=True)
    ]

    client.upsert(collection_name=COLLECTION_NAME, wait=True, points=points)
    print(f"[Qdrant] 已写入 {len(points)} 条文档")


def hybrid_search(
    client: QdrantClient,
    query_vector: list[float],
    *,
    category: str,
    limit: int = 2,
) -> list[Any]:
    """
    混合检索 = 向量相似度排序 + 结构化过滤。

    等价 SQL 直觉：
      SELECT * FROM articles
      WHERE category = 'tech'
      ORDER BY cosine_similarity(embedding, :query_vec) DESC
      LIMIT 2;

    query_filter 在 ANN 搜索前/中缩小候选集，避免「语义很像但业务上不该返回」的结果。
    """
    return client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category),
                )
            ]
        ),
        limit=limit,
        # 可选：with_payload=True（默认）返回元数据；score_threshold 可设最低相似度门槛
    )


def print_hits(hits: list[Any], *, title: str) -> None:
    """格式化打印检索结果，便于肉眼对比 score 与 payload。"""
    print(f"\n--- {title} ---")
    if not hits:
        print("（无结果）")
        return
    for rank, hit in enumerate(hits, start=1):
        payload = hit.payload or {}
        print(
            f"#{rank}  id={hit.id}  score={hit.score:.4f}  "
            f"title={payload.get('title')}  views={payload.get('views')}"
        )


def build_rag_context(hits: list[Any]) -> str:
    """
    把检索到的文档拼成 LLM 上下文（RAG 的 Retrieval 步到此为止）。

    下一步通常是：
      prompt = system + user_question + context
      answer = llm.chat(prompt)
    本示例不调用 LLM，只打印 context 让你看到会喂给模型的内容长什么样。
    """
    blocks: list[str] = []
    for hit in hits:
        payload = hit.payload or {}
        blocks.append(
            f"[doc id={hit.id} score={hit.score:.3f}]\n"
            f"Title: {payload.get('title')}\n"
            f"Content: {payload.get('content')}"
        )
    return "\n\n".join(blocks)


def main() -> None:
    print("=" * 60)
    print("向量数据库完整示例：Embedding → Qdrant → 混合检索 → RAG Context")
    print("=" * 60)

    # -------------------------------------------------------------------------
    # 1. 加载 Embedding 模型（真正把「文本」变成「向量」的组件）
    # -------------------------------------------------------------------------
    print(f"\n[Embedding] 加载模型: {EMBEDDING_MODEL_NAME}")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    vector_size = model.get_sentence_embedding_dimension()
    print(f"[Embedding] 输出维度: {vector_size}")

    # -------------------------------------------------------------------------
    # 2. 连接 Qdrant 并建表（Collection）
    # -------------------------------------------------------------------------
    client = create_qdrant_client()
    recreate_collection(client, vector_size)

    # -------------------------------------------------------------------------
    # 3. 向量化样例文档并入库
    # -------------------------------------------------------------------------
    texts = [build_text_for_embedding(article) for article in SAMPLE_ARTICLES]
    doc_vectors = embed_texts(model, texts)
    upsert_articles(client, SAMPLE_ARTICLES, doc_vectors)

    # -------------------------------------------------------------------------
    # 4. 用户提问 → 问题向量 → 混合检索
    # -------------------------------------------------------------------------
    print(f"\n[Query] 用户问题: {USER_QUERY!r}")
    query_vector = embed_texts(model, [USER_QUERY])[0]

    # 4a. 仅向量检索（无过滤）：看全局语义最接近谁
    pure_vector_hits = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=2,
    )
    print_hits(pure_vector_hits, title="纯向量检索 Top-2（无 category 过滤）")

    # 4b. 混合检索：只要 tech 类文章
    hybrid_hits = hybrid_search(
        client,
        query_vector,
        category="tech",
        limit=2,
    )
    print_hits(hybrid_hits, title='混合检索 Top-2（category 必须为 "tech"）')

    # -------------------------------------------------------------------------
    # 5. 组装 RAG 上下文（演示 Retrieval 的输出）
    # -------------------------------------------------------------------------
    rag_context = build_rag_context(hybrid_hits)
    print("\n--- 将注入 LLM 的 RAG Context（节选）---")
    print(rag_context)

    print("\n[Done] 流程结束。若要持久化数据，请用 Docker 起 Qdrant 并设置 QDRANT_URL。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
