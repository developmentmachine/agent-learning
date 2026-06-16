# Hermes Agent：高级 Session 上下文管理与大模型交互设计

在像 Hermes 或 Gemini CLI 这样的高级 Agent 中，维持长时间的连续对话（Session）并且让大语言模型（LLM）理解当前的任务状态是核心能力之一。随着模型能力的增强和使用场景的复杂化，简单地“把所有对话追加并扔给模型”会面临成本、延迟和上下文溢出的问题。

以下是 Hermes Agent 管理 Session 上下文的高级设计思路，特别是如何解决长期记忆与上下文溢出之间的矛盾，非常适合自己在开发高级 Agent 时借鉴。

---

## 一、 Hermes 是如何传递 Session 信息的？

Hermes 把一个 Session 的上下文分成了**静态**和**动态**两部分，组合后传给大模型：

### 1. System Prompt 的“冻结快照”（Frozen Snapshot）
在每次 Session 启动时，Hermes 会读取本地的 `MEMORY.md`（环境与事实）、`USER.md`（用户画像）以及所有 Skill 的摘要索引（仅包含名称和一句话描述），将它们拼装成 System Prompt。
- **关键机制**：这个 System Prompt 在整个 Session 期间是**冻结的（Cached）**。即使在对话中途 Agent 学习到了新知识并更新了 `MEMORY.md`，System Prompt 也不会立刻改变（下一次 Session 才生效）。
- **目的**：最大化利用大模型厂商的 **Prefix Cache（前缀缓存）** 技术。因为 System Prompt 占据了大量 Token 且保持不变，冻结它可以大幅降低多轮对话的 Token 成本，并显著提升首字响应速度（TTFT）。

### 2. Messages 列表的标准追加与 Tool-Role 注入
对于当前 Session 内的直接对话，Hermes 会维护一个标准的 `messages` 数组，包含 `user` 和 `assistant` 的多轮交互。
- **按需召回机制（Tool-Role 注入）**：长文本或跨 Session 的历史对话不会一直驻留在内存中。大模型如果需要了解深层细节或过去的聊天，必须主动调用 Tool：
  - 如果想查阅长篇经验/SOP，模型调用 `skill_view(name)` 工具。
  - 如果想回忆几天前的某次对话，模型调用 `session_search(query)` 工具（底层是 SQLite FTS5 引擎）。
- **结果注入**：工具的返回结果会作为 `role: "tool"` 追加到当前 Session 的 `messages` 数组末尾，从而将离线知识转化为当前上下文。

---

## 二、 如果自己开发 Agent，如何借鉴它的设计思路？

你可以直接“抄作业”，这套设计完美解决了长期记忆与上下文溢出之间的矛盾。核心可以借鉴以下 4 点：

### 1. 放弃“全量 System Prompt”，采用分级披露（Progressive Disclosure）
如果你有很多 SOP（Standard Operating Procedures）文档或者业务知识，不要在开头全塞给大模型，这会破坏 Prefix Cache 并导致注意力失焦。
- **Tier 0（常驻）**：在 System prompt 中只列出目录和摘要。例如：`<available_skills>- deploy-k8s: 描述... - fix-bug: 描述...</available_skills>`。
- **Tier 1（按需加载全文）**：提供一个 `read_skill_detail(name)` 工具。大模型通过目录发现匹配任务后，调用工具，将这部分详细知识作为 Tool 消息拉入当前轮次的上下文中。

### 2. 读写分离的「双轨记忆」系统
不要把所有的记忆混在一起，Hermes 将记忆拆分为两类，非常利于治理：
- **声明式记忆（事实类）**：如用户的习惯（"偏好使用 Python"）、项目的约定（"主干分支是 main"）。存放在字数受限的文件中（比如限制 2000 字符），每次 Session 启动全量加载到 System Prompt 中。如果快满了，强制模型自己去做摘要压缩（Consolidate）。
- **程序式记忆（流程类）**：即各种具体任务怎么做（如踩坑记录、Debug 流程）。按任务分类存成 Markdown 文件（即 Skills），通过上述的分级披露工具动态加载。

### 3. 引入 Background Review（后台复盘机制）
为了让 Agent “越用越聪明”又绝对不影响响应用户的速度：
- 在给用户发完最终回复后，在后台开启一个守护线程（Daemon），Fork 出一个**没有上下文压力、拥有“写文件”权限的子 Agent**。
- 将刚才的对话快照传给子 Agent，让它评估：“这轮对话中有没有值得沉淀的用户偏好或踩坑经验？”
- 如果有，子 Agent 自己调用 `memory(add)` 或 `skill_manage(patch)` 写入硬盘。
- **优势**：用户完全感觉不到延迟，但下一次对话时（或开启新 Session 时），Agent 已经默默进化了。

### 4. 本地数据库承载历史对话，模型自主“检索”
对于跨 Session 或极其冗长的单次 Session，内存数组是存不下的：
- 用轻量级数据库（如 **SQLite + 全文检索索引 FTS5**）把所有流水账存起来。
- 给大模型配备类似 `search_past_conversations(query)` 和 `get_messages_around(message_id, window=5)` 的工具。
- 这让大模型具备了在海量历史记录中“搜索”和“上下滚动查阅”的能力，无需把整个 Session 历史毫无保留地发给 API，实现了记忆的无限扩展。

---
*附：配套的高级代码 Demo 位于 `demos/hermes-session-context-management` 目录中，包含了分级披露、双轨记忆、后台复盘和本地 DB 检索的模拟实现。*
