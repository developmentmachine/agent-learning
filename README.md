# agent-learning

围绕 **自研 Agent** 的机制学习与可运行 Demo，主线是 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的 Skill 加载、Memory 召回与闭环学习。文档 + 本地 Python Demo 对照阅读，**不需要 API Key** 即可跑通大部分流程。

---

## 怎么读这个仓库

### 一句话地图

| 你想搞懂什么 | 先读 | 再跑 |
|--------------|------|------|
| System prompt 怎么分层、三套模板长什么样 | [docs/agent-system-prompt-templates.md](docs/agent-system-prompt-templates.md) | `demos/hermes-skill-loader/scenario-templates.py` |
| Skill 为何不全塞进 prompt、怎么按需加载 | [docs/hermes-skill-dynamic-loading.md](docs/hermes-skill-dynamic-loading.md) | `demos/hermes-skill-loader/scenario.py` |
| Memory 进 prompt 还是进 tool message | [docs/hermes-closed-loop-learning.md](docs/hermes-closed-loop-learning.md) §3–4 | `demos/hermes-memory-recall/demo.py` |
| 后台审查如何写 memory/skill、为何 fork | [docs/hermes-closed-loop-learning.md](docs/hermes-closed-loop-learning.md) §5+ | `demos/hermes-closed-loop-learning/demo.py` |

### 推荐学习路径（约 1–2 小时）

```
1. agent-system-prompt-templates.md     ← 总览：prompt 四层 + Coding/Oncall/Review 模板
        ↓
2. hermes-skill-dynamic-loading.md      ← 程序式记忆：Progressive Disclosure
        ↓
3. demos/hermes-skill-loader/           ← 动手：索引 → skill_view → references
        ↓
4. hermes-closed-loop-learning.md       ← 声明式记忆 + 闭环学习
        ↓
5. demos/hermes-memory-recall/          ← 三种 recall 路径
        ↓
6. demos/hermes-closed-loop-learning/   ← Background Review 模拟（可选深入）
```

若时间紧，只走 **1 → 2 → 3** 即可建立「prompt 拼装 + skill 按需加载」的完整图景。

---

## 目录结构

```
agent-learning/
├── README.md                 ← 本文件（学习导航）
├── docs/                     ← 原理与实践文档（中文）
│   ├── agent-system-prompt-templates.md
│   ├── hermes-skill-dynamic-loading.md
│   └── hermes-closed-loop-learning.md
└── demos/                    ← 可运行最小实现（对照上游 Hermes 注释）
    ├── hermes-skill-loader/      Skill 加载 + 15 个模板 skill 样例
    ├── hermes-memory-recall/     Memory 冻结快照 vs tool 召回
    └── hermes-closed-loop-learning/  闭环学习 + Background Review
```

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [agent-system-prompt-templates.md](docs/agent-system-prompt-templates.md) | System prompt 四层模型；Coding / Oncall / Review 三套可落地模板；与 Cursor、Claude Code、OpenClaw 对照 |
| [hermes-skill-dynamic-loading.md](docs/hermes-skill-dynamic-loading.md) | Tier-0 索引、`skill_view`、`skill_manage`、slash command、缓存与安全防护 |
| [hermes-closed-loop-learning.md](docs/hermes-closed-loop-learning.md) | Memory vs Skill 分工、冻结快照、Background Review、Curator、nudge 触发 |

文档之间已互相链接；从任意一篇顶部的「相关文档」可跳转。

---

## Demo 快速开始

环境：**Python 3.10+**，无第三方依赖。

### 1. Skill 加载（建议第一个跑）

```bash
cd demos/hermes-skill-loader

# 三套模板 walkthrough：general / oncall / review
python scenario-templates.py

# 原有完整生命周期：create / patch / 安全扫描
python scenario.py

# 查看 Tier-0 索引（eager 模式）
python demo.py --show-index

# 交互式 mock agent（关键词触发 tool，无需 LLM）
python demo.py
```

**Skill 样例目录**（对应文档三套模板）：

- `skills/general/` — repo-explore, implement-feature, run-tests, debug-build
- `skills/oncall/` — incident-triage, log-search, trace-analysis, …
- `skills/review/` — code-review, pr-diff-scan, security-review, …

**Stable prompt 片段**（可复制进真实 Agent）：`prompts/stable-{coding,oncall,review}.md`

### 2. Memory 召回三条路径

```bash
cd demos/hermes-memory-recall
python demo.py
```

演示：声明式 memory → system prompt 冻结快照；`session_search` / `skill_view` → tool message。

### 3. 闭环学习（进阶）

```bash
cd demos/hermes-closed-loop-learning
python demo.py
```

演示：前台回合结束 → Background Review fork → `memory` / `skill_manage` 写入。

---

## 核心概念速查

| 概念 | 含义 |
|------|------|
| **Progressive Disclosure** | 会话启动只注入 skill 的 name+description；正文通过 `skill_view` 按需加载 |
| **Stable / Context / Volatile** | System prompt 三层：不变纪律 → 项目文件 → 易变 memory/日期 |
| **Frozen snapshot** | 会话中途 memory 写入落盘，但不立刻改 system prompt（保 prefix cache） |
| **Declarative vs Procedural** | MEMORY/USER = 是谁/环境怎样；SKILL = 这类事怎么做 |
| **Background Review** | 用户看到回复后，fork 子 Agent 审查是否该 patch memory/skill |

---

## 与上游 Hermes 的关系

Demo 是对 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 关键路径的**缩小可运行复刻**，源码对照见各文档末尾「源码对照索引」及各 demo 文件头注释（如 `agent/system_prompt.py`、`tools/skills_tool.py`）。

本仓库**不是** Hermes 的安装包；要跑完整 Hermes 请跟上游文档。

---

## 调研延伸（仓库外）

| 主题 | 参考 |
|------|------|
| Claude Code prompt 拼装 | [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts) |
| OpenClaw system prompt | [docs.openclaw.ai/concepts/system-prompt](https://docs.openclaw.ai/concepts/system-prompt) |
| Hermes 上游 | [hermes-agent.nousresearch.com/docs](https://hermes-agent.nousresearch.com/docs) |

---

*最后更新：2026-06-10*
