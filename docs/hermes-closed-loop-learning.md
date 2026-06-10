# Hermes 闭环学习与记忆进化

> 整理日期：2026-06-09  
> 源码参考：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)  
> 本地 Demo：`demos/hermes-closed-loop-learning/`  
> 相关文档：[Hermes Skill 动态加载](./hermes-skill-dynamic-loading.md)（程序式记忆的加载侧）

---

## 目录

1. [核心结论](#1-核心结论)
2. [架构总览](#2-架构总览)
3. [双轨记忆](#3-双轨记忆)
4. [读写分离与冻结快照](#4-读写分离与冻结快照)
5. [Background Review（每轮后台审查）](#5-background-review每轮后台审查)
6. [Nudge 触发机制](#6-nudge-触发机制)
7. [Provenance 写入来源分流](#7-provenance-写入来源分流)
8. [Curator（技能库长期治理）](#8-curator技能库长期治理)
9. [完整闭环时间线](#9-完整闭环时间线)
10. [与 session_search 的关系](#10-与-session_search-的关系)
11. [本地 Demo 使用指南](#11-本地-demo-使用指南)
12. [源码对照索引](#12-源码对照索引)
13. [设计 Checklist](#13-设计-checklist)

---

## 1. 核心结论

Hermes 的「闭环学习」不是训练模型权重，而是 **跨会话持久化 + 后台自审查 + 周期性治理** 三条链路叠加：

| 链路 | 做什么 | 何时运行 |
|------|--------|----------|
| **声明式记忆** | `MEMORY.md` / `USER.md` 记录环境与用户画像 | 前台或 Background Review 写入；**下次会话**进 prompt |
| **程序式记忆** | `~/.hermes/skills/` 记录某类任务怎么做 | 同上；正文经 [Skill 动态加载](./hermes-skill-dynamic-loading.md) 按需读取 |
| **Background Review** | Fork 子 Agent 审查本轮对话，决定是否写 memory / patch skill | **每轮用户回复交付后**，daemon 线程 |
| **Curator** | 对 agent-created skill 做 stale / archive / 合并 | 空闲 + 间隔（默认 7 天） |

**一句话**：前台专心完成任务；后台 Fork 负责「学」；Curator 负责「忘」（archive 可恢复）。

### 六条设计要点（速查）

| # | 要点 | 机制 |
|---|------|------|
| 1 | **读写分离** | 学习在后台 Fork，不阻塞用户看到回复 |
| 2 | **冻结快照** | memory 写入当轮落盘，但 **不进** 当轮 system prompt（保 prefix cache） |
| 3 | **分级披露** | skill 索引常驻，正文 `skill_view` 按需（见 Skill 文档 §3） |
| 4 | **双轨记忆** | memory = 是谁/环境怎样；skill = 这类事怎么做 |
| 5 | **Provenance 分流** | 只有 `background_review` Fork 创建的 skill 才归 Curator 管 |
| 6 | **创造 + 修剪** | Background Review 沉淀经验；Curator 归档/合并冗余 |

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│  Session Start                                                  │
│  ├─ 加载 MEMORY.md + USER.md → 冻结进 system prompt             │
│  └─ build_skills_system_prompt() → skill 索引（name+description）│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Foreground Turn（前台主 Agent）                                 │
│  User → LLM + tools → 回复用户                                   │
│  期间可主动调用 memory / skill_manage / skill_view               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  turn_finalizer：Nudge 判定                                      │
│  memory 每 N 轮？  skill 每 M 次工具迭代且本轮未 skill_manage？   │
└─────────────────────────────────────────────────────────────────┘
                              │ 若触发
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Background Review（daemon 线程）                                │
│  Fork AIAgent · 工具白名单 {memory, skill_manage, skills_*}      │
│  继承父 Agent cached system prompt · 回放对话快照                 │
│  → memory(add/replace) · skill_manage(patch/create/write_file)   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  跨会话 + 长期                                                   │
│  新会话：memory 快照刷新 · skill 索引重扫                         │
│  Curator（空闲时）：.usage.json → stale → archive · LLM 合并     │
└─────────────────────────────────────────────────────────────────┘
```

### 关键模块（Hermes 源码）

| 模块 | 文件 | 职责 |
|------|------|------|
| 声明式记忆 | `tools/memory_tool.py` | `MemoryStore`、add/replace/remove、字符上限 |
| 程序式记忆 | `tools/skill_manager_tool.py` | `skill_manage` create/patch/edit/… |
| 写入来源 | `tools/skill_provenance.py` | `ContextVar` 区分 foreground / background_review |
| 回合 nudge | `agent/turn_context.py` | memory nudge 计数 |
| 回合结束触发 | `agent/turn_finalizer.py` | skill nudge + `_spawn_background_review` |
| 后台 Fork | `agent/background_review.py` | 审查 prompt、Fork 生命周期、结果摘要 |
| Skill 遥测 | `tools/skill_usage.py` | `.usage.json`、bump_view/patch、生命周期状态 |
| 长期治理 | `agent/curator.py` | 自动转换 + LLM 审查 pass |
| Skill 按需读 | `tools/skills_tool.py` | `skill_view` → bump_view |

---

## 3. 双轨记忆

Hermes 刻意把「事实」和「流程」分开存储，避免把所有东西都塞进 bounded memory。

### 声明式：MEMORY.md + USER.md

| 文件 | 存什么 | 字符上限（默认） |
|------|--------|------------------|
| `MEMORY.md` | 环境、项目约定、踩坑日记、已完成事项 | 2,200（~800 tokens） |
| `USER.md` | 用户偏好、沟通风格、角色与时区 | 1,375（~500 tokens） |

- 条目以 `§` 分隔，可 multiline
- `memory` tool：`add` / `replace` / `remove`；`replace`/`remove` 用 **短子串** 匹配唯一条目
- `target="memory"` 或 `target="user"`
- 满容时 tool 返回错误，要求 agent 先 consolidate 再 add

**该存什么**：用户偏好、环境事实、项目约定、可复用的教训摘要。  
**不该存什么**：大段日志、一次性的临时路径、易搜索的常识、已在 SOUL.md 里的内容。

### 程序式：Skills（SKILL.md）

- 窄而 actionable：某 **类任务** 的步骤、pitfall、verification
- 经 Progressive Disclosure 加载（索引 → 全文 → references），见 [Skill 文档 §3](./hermes-skill-dynamic-loading.md#3-progressive-disclosure-分级披露)
- 前台复杂任务完成后，或 Background Review 认为有 class-level 信号时，经 `skill_manage` 写入

### 分工原则（Background Review prompt 中的显式规则）

| 维度 | memory | skill |
|------|--------|-------|
| 用户是谁、偏好什么 | ✅ `USER.md` | 可选嵌入相关 skill 正文 |
| 用户抱怨「你怎么做这件事」 | 可记画像 | **必须** patch  governing skill |
| 调试路径、workaround | 摘要级事实 | ✅ `references/` 或 skill 步骤 |
| 一次性任务叙事 | ❌ | ❌ |

用户说「别那么啰嗦」→ 既可能进 `USER.md`，更应 patch 本轮相关的 skill，让 **下次加载 skill 时就带上风格约束**。

---

## 4. 读写分离与冻结快照

### 读写分离

- **读路径（热）**：前台 Agent 推理 → 立刻回复用户
- **写路径（冷）**：`turn_finalizer` 在 `final_response` 交付 **之后** 才 `threading.Thread` 启动 Background Review
- Fork 与主会话 **隔离**：独立 iteration budget、stdout 重定向、`suppress_status_output`、禁止 compression（避免污染父 session 压缩树）

主对话和 prompt prefix cache **不被** 审查 Fork 改写。

### 冻结快照（Frozen Snapshot）

`MemoryStore` 维护两套状态（上游 `tools/memory_tool.py`）：

| 状态 | 用途 | 何时更新 |
|------|------|----------|
| `_system_prompt_snapshot` | 注入 system prompt | **仅** `load_from_disk()` / 会话启动 |
| `memory_entries` / `user_entries` | tool 响应当前真实内容 | 每次 `memory` tool 调用 |

因此：

- 会话中途 `memory(add)` → 文件立刻更新，tool 结果可见，**但 system prompt 里仍是旧快照**
- 下一轮 **新会话** → 重新 `load_from_disk()`，新条目进入 prompt

Skill 索引同理：`skill_manage` 成功后会 `clear_skills_system_prompt_cache`，但已发出的请求仍用旧 prefix；新 turn / 新会话重建索引。

**为何这样设计**：LLM provider 的 **prefix cache** 按 system prompt 字节精确匹配；mid-session 改 memory 块会导致 cache miss，成本上升。

---

## 5. Background Review（每轮后台审查）

### 做什么

`agent/background_review.py` 在 daemon 线程中：

1. `AIAgent(..., skip_memory=True)` Fork，继承父 runtime（provider/model/credentials/**`_cached_system_prompt`**）
2. `set_thread_tool_whitelist({memory, skill_manage, skills_list, skill_view, …})`
3. `run_conversation(conversation_history=messages_snapshot, user_message=审查prompt)`
4. 扫描 Fork 产出的 tool 结果 → 打印 `💾 Self-improvement review: Memory updated · Skill 'x' patched`

### 审查 prompt 策略（摘要）

Fork 收到的指令（`_SKILL_REVIEW_PROMPT` / `_COMBINED_REVIEW_PROMPT`）核心要求：

- **要主动**：多数会话应至少有一次 skill 更新；「什么都不做」是 missed opportunity
- **类级 skill**：`debugging-workflow` ✅；`fix-pr-1234-today` ❌
- **更新优先级**：
  1. Patch **本轮已加载** 的 skill
  2. Patch 已有 umbrella skill
  3. `write_file` → `references/` / `templates/` / `scripts/`
  4. 最后才 `create` 新 umbrella
- **禁止固化**：环境缺 binary、某工具「坏了」、已自行恢复的单次错误
- **protected**：bundled / hub-installed skill 不可 edit；pinned skill 可 patch 不可删

### Fork 关键约束

| 约束 | 原因 |
|------|------|
| 继承 `_cached_system_prompt` | 命中同一 prefix cache（约 26% 成本节省） |
| `_memory_nudge_interval = 0` | 防止 Fork 再触发嵌套 review |
| `compression_enabled = False` | 避免与父 session 共享 session_id 时压缩竞态 |
| `skip_memory=True` | 不写外部 memory provider（Honcho/Mem0 等） |
| terminal 自动 deny | 防止 TUI 死锁 |

---

## 6. Nudge 触发机制

两种 nudge **独立计数、独立触发**，在 `turn_finalizer` 合并决定是否 spawn review。

### Memory nudge（按用户轮次）

`agent/turn_context.build_turn_context`：

```
每 turn 开始：
  _turns_since_memory += 1
  if _turns_since_memory >= _memory_nudge_interval:
      should_review_memory = True
      _turns_since_memory = 0
```

默认 interval 由 Agent 配置决定（常见为每若干 **user turn** 一次）。

### Skill nudge（按工具迭代）

`agent/conversation_loop` 每 API 迭代：

```
if skill_manage 不在本轮被调用:
  _iters_since_skill += 1
```

`agent/turn_finalizer` 回合结束：

```
if _iters_since_skill >= _skill_nudge_interval:
  should_review_skills = True
  _iters_since_skill = 0
```

默认约 **每 10 次工具迭代** 且本轮未使用 `skill_manage` 时触发 skill 审查。  
若前台已 `skill_manage`，计数器重置，避免重复审查。

### 触发条件汇总

| 条件 | Memory Review | Skill Review |
|------|---------------|--------------|
| 本轮有 `final_response` 且未 interrupt | 需要 | 需要 |
| 对应 tool 在 valid_tool_names | `memory` | `skill_manage` |
| 计数达阈值 | `_turns_since_memory` | `_iters_since_skill` |

---

## 7. Provenance 写入来源分流

`tools/skill_provenance.py` 用 `ContextVar` 标记当前 tool 执行上下文：

| `write_origin` | 含义 |
|----------------|------|
| `foreground` | 正常 CLI / gateway / 用户对话中的 tool |
| `background_review` | Background Review Fork |

### 对 skill 生命周期的影响

`skill_manager_tool.py` 在 `create` 成功时：

```python
if action == "create":
    if is_background_review():
        mark_agent_created(name)   # .usage.json: created_by=agent
```

| 创建方式 | Curator 是否管理 |
|----------|------------------|
| Background Review Fork `create` | ✅ 是（agent-created） |
| 前台用户让 Agent `skill_manage(create)` | ❌ 否（用户资产） |
| 用户手写 SKILL.md | ❌ 否 |
| Hub / bundled 安装 | ❌ 永不 |

**设计意图**：自主沉淀的 skill 可以归档合并；用户显式创建的 skill 不被后台误删。

---

## 8. Curator（技能库长期治理）

Background Review 解决「学不够」；Curator 解决「学太多、太散」。

### 遥测：`.usage.json`

路径：`~/.hermes/skills/.usage.json`（sidecar，不写进 SKILL.md frontmatter）

| 字段 | 何时更新 |
|------|----------|
| `view_count` / `last_viewed_at` | `skill_view` |
| `use_count` / `last_used_at` | skill 进入对话 prompt 路径 |
| `patch_count` / `last_patched_at` | `skill_manage` patch/edit/write_file/remove_file |
| `state` | `active` → `stale` → `archived` |
| `pinned` | `hermes curator pin` |
| `agent_created` | 仅 background_review create |

### 运行时机

非系统 cron，而是 **inactivity check**：

- CLI 会话启动 / gateway cron tick
- 条件：`now - last_run_at >= interval_hours`（默认 168h）**且** agent idle ≥ `min_idle_hours`（默认 2h）

### 两阶段

**阶段 1 — 确定性（无 LLM）**

| 闲置天数 | 状态转换 |
|----------|----------|
| ≥ 30（`stale_after_days`） | `active` → `stale` |
| ≥ 90（`archive_after_days`） | 移入 `~/.hermes/skills/.archive/` |

pinned skill 跳过所有自动转换。

**阶段 2 — LLM 审查（forked AIAgent，max_iterations=8）**

- 输入：agent-created skill 列表 + usage 统计
- 工具：仅现有 `skills_list` / `skill_view` / `skill_manage patch` / `terminal mv`
- 动作：合并重叠 skill、patch 漂移、归档过时项
- **不 auto-delete**；archive 可用 `hermes curator restore` 恢复

### 默认配置

```yaml
curator:
  enabled: true
  interval_hours: 168      # 7 天
  min_idle_hours: 2
  stale_after_days: 30
  archive_after_days: 90
  prune_builtins: true     # 可选归档长期未用的 bundled skill
```

---

## 9. 完整闭环时间线

```
T0  会话启动
    ├─ MEMORY.md / USER.md → 冻结快照注入 system prompt
    └─ skill 索引注入（仅 name + description）

T1  用户任务（例：「部署 k8s，回复简洁些」）
    ├─ skill_view("deploy-k8s") → bump_view
    ├─ 多次工具调用完成任务
    └─ 前台回复用户

T2  turn_finalizer
    ├─ skill nudge 达标 → should_review_skills = True
    └─ spawn_background_review(messages_snapshot)

T3  Background Review Fork
    ├─ memory(add, target=user)："偏好简洁"
    ├─ skill_manage(patch, deploy-k8s)：增加 pitfall
    └─ 用户看到 💾 Self-improvement review: ...

T4  同会话后续 turn
    ├─ memory 快照仍不变（T0 冻结）
    └─ skill 文件已更新 → 再次 skill_view 可读新内容

T5  新会话
    ├─ memory 快照刷新 → 用户偏好常驻
    └─ skill 索引含 patch 后的 description/正文

T6  数周后（空闲 + interval）
    └─ Curator：长期未用的 agent-created skill → archive
```

---

## 10. 与 session_search 的关系

| | Persistent Memory + Skills | session_search |
|---|---------------------------|----------------|
| 容量 | bounded（~1.3k tokens memory） | 全量会话 SQLite FTS5 |
| 注入 | 每会话固定进 prompt | 按需查询 |
| 用途 | 关键事实、流程 | 「上周聊过 X 吗」 |
| 进化 | agent 主动 curated | 自动存储，不 curated |

Memory/Skill 是 **进化写入** 路径；session_search 是 **回忆检索** 路径，互补而非替代。

---

## 11. 本地 Demo 使用指南

### 目录结构

```
demos/hermes-closed-loop-learning/
├── learning_loop.py    # MemoryStore、UsageTracker、Background Review 模拟
├── demo.py             # 六阶段 walkthrough（无需 API Key）
└── _sandbox/           # 运行时生成（memories/、skills/、.usage.json）

demos/hermes-skill-loader/          # 配套：Skill 加载 + skill_manage
├── skill_loader.py
├── scenario.py
└── demo.py
```

### 推荐学习路径（15 分钟）

```bash
# ① 闭环全链路（memory + review + curator）
cd demos/hermes-closed-loop-learning
python demo.py

# ② Skill 加载与 skill_manage 细节
cd ../hermes-skill-loader
python scenario.py
```

### Demo 阶段与上游对照

| demo.py Phase | 模拟的上游行为 |
|---------------|----------------|
| 0 | 空 memory 冻结快照 + skill Tier-0 索引 |
| 1 | 前台 turn + nudge 计数 |
| 2 | `background_review._run_review_in_thread` |
| 3 | `USER.md` + agent-created skill + `.usage.json` |
| 4 | **新会话** memory 快照刷新、索引出现新 skill |
| 5 | `skill_view` + `bump_view` |
| 6 | Curator 确定性 `stale → archive`（模拟 95 天闲置） |

Demo 用规则引擎 `detect_learning_signals()` 代替 LLM Fork；结构与上游一致，便于无 Key 本地跑通。

### 与 Skill Demo 的分工

| 主题 | 文档 | Demo |
|------|------|------|
| 索引 / skill_view / slash | [Skill 动态加载](./hermes-skill-dynamic-loading.md) | `hermes-skill-loader/` |
| memory / review / curator | 本文 | `hermes-closed-loop-learning/` |

---

## 12. 源码对照索引

| 概念 | Hermes 源码 | 本地 Demo |
|------|-------------|-----------|
| 声明式 memory | `tools/memory_tool.py` :: `MemoryStore` | `learning_loop.py` :: `MemoryStore` |
| memory tool | `memory(action=add/replace/remove)` | `MemoryStore.tool_memory()` |
| 程序式 skill 写 | `tools/skill_manager_tool.py` | `hermes-skill-loader/skill_loader.py` :: `tool_skill_manage` |
| 写入来源 | `tools/skill_provenance.py` | `WriteOriginContext` |
| memory nudge | `agent/turn_context.py` | `should_trigger_review()` memory 分支 |
| skill nudge + spawn | `agent/turn_finalizer.py` | `should_trigger_review()` skill 分支 |
| Background Review | `agent/background_review.py` | `run_background_review()` |
| usage 遥测 | `tools/skill_usage.py` | `UsageTracker` |
| 生命周期转换 | `skill_usage.apply_automatic_transitions` | `UsageTracker.apply_lifecycle()` |
| Curator 编排 | `agent/curator.py` | demo Phase 6（仅确定性阶段） |
| skill 按需读 | `tools/skills_tool.py` | `HermesSkillLoader.tool_skill_view()` |

---

## 13. 设计 Checklist

自建带闭环学习的 Agent 时，可按此清单自检。

### 双轨记忆

- [ ] 声明式存储有 **硬字符/token 上限**，满容要求 consolidate
- [ ] 程序式存储按 **任务类** 组织，而非一次性会话 artifact
- [ ] 明确 memory vs skill 分工（偏好/事实 vs 流程/pitfall）

### 读写分离

- [ ] 学习/审查在 **用户可见回复之后** 异步运行
- [ ] 审查 Fork **不修改** 主会话 messages / system prompt cache
- [ ] 审查工具 **白名单** 限制（仅 memory + skill 管理）

### 冻结快照

- [ ] memory 注入 prompt 的是 **会话启动快照**，非 live 文件
- [ ] mid-session 写入立即落盘，tool 响应反映 live 状态
- [ ] 文档中向用户/开发者说明「同会话内 memory 可能滞后一轮显示」

### 分级披露（Skill 侧）

- [ ] 见 [Skill 文档 §14 Checklist](./hermes-skill-dynamic-loading.md#14-设计-checklist)

### Provenance

- [ ] 区分 **自主沉淀** vs **用户指令创建** 的资产
- [ ] 仅自主沉淀纳入自动治理（archive/merge）
- [ ] `ContextVar` 或等价机制在 tool handler 内可读

### 创造 + 修剪

- [ ] 有 **post-turn review**（nudge + Fork）负责沉淀
- [ ] 有 **periodic curator** 负责 stale/archive/合并
- [ ] archive **可恢复**；不 silent delete
- [ ] usage 遥测：`view` / `patch` / `last_*_at` 驱动生命周期
- [ ] pin 机制保护关键 skill

### 安全

- [ ] memory / skill 写入前 **injection scan**（进入 system prompt 的内容）
- [ ] skill 写入 **atomic write** + 失败 rollback
- [ ] Background Fork 危险 terminal 命令 **auto-deny**

### 可观测

- [ ] 审查完成后用户可见摘要（如 `Self-improvement review: …`）
- [ ] Curator 每次运行写 `~/.hermes/logs/curator/<ts>/REPORT.md`
- [ ] `hermes curator status` 等价能力（LRU、pinned、last run）

---

## 附录：Background Review 伪代码

```python
def finalize_turn(agent, messages, final_response):
    # 1. 先交付用户回复（热路径结束）
    result = build_result(final_response, messages)

    # 2. Nudge 判定
    should_review_memory = agent.turns_since_memory >= agent.memory_nudge_interval
    should_review_skills = agent.iters_since_skill >= agent.skill_nudge_interval

    # 3. 冷路径：异步审查
    if final_response and not interrupted and (should_review_memory or should_review_skills):
        threading.Thread(
            target=run_background_review,
            args=(agent, list(messages), should_review_memory, should_review_skills),
            daemon=True,
        ).start()

    return result


def run_background_review(agent, snapshot, review_memory, review_skills):
    fork = AIAgent(
        inherit_runtime_from=agent,
        cached_system_prompt=agent._cached_system_prompt,  # prefix cache 对齐
        tool_whitelist={"memory", "skill_manage", "skills_list", "skill_view"},
        memory_nudge_interval=0,
        skill_nudge_interval=0,
    )
    fork.set_write_origin("background_review")
    prompt = COMBINED_REVIEW_PROMPT if (review_memory and review_skills) else ...
    fork.run_conversation(conversation_history=snapshot, user_message=prompt)
    summarize_and_print(fork.tool_results)
```

---

*文档与 Demo 基于 Hermes Agent 开源实现提炼，已脱敏。Skill 加载机制见 [hermes-skill-dynamic-loading.md](./hermes-skill-dynamic-loading.md)。*
