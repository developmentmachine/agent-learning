# Hermes Skill 动态加载原理与实践

> 整理日期：2026-06-09  
> 源码参考：[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)  
> 本地 Demo：`demos/hermes-skill-loader/`  
> 相关文档：[Hermes 闭环学习与记忆进化](./hermes-closed-loop-learning.md)（memory / Background Review / Curator）· [Agent System Prompt 模板](./agent-system-prompt-templates.md)（Coding / Oncall / Review 落地骨架）

---

## 目录

1. [核心结论](#1-核心结论)
2. [架构总览](#2-架构总览)
3. [Progressive Disclosure 分级披露](#3-progressive-disclosure-分级披露)
4. [存储与发现机制](#4-存储与发现机制)
5. [三种加载触发路径](#5-三种加载触发路径)
6. [Tool 层实现](#6-tool-层实现)
7. [System Prompt 索引构建](#7-system-prompt-索引构建)
8. [Slash Command 机制](#8-slash-command-机制)
9. [预处理与安全](#9-预处理与安全)
10. [缓存与重载策略](#10-缓存与重载策略)
11. [与 Cursor Skills 对比](#11-与-cursor-skills-对比)
12. [本地 Demo 使用指南](#12-本地-demo-使用指南)
13. [源码对照索引](#13-源码对照索引)
14. [设计 Checklist](#14-设计-checklist)

---

## 1. 核心结论

Hermes 的 Skill **不是**在会话启动时把全部 `SKILL.md` 塞进 system prompt，而是采用 **Progressive Disclosure（分级披露）**：

| 阶段 | 加载什么 | 何时加载 |
|------|----------|----------|
| 会话启动 | `name` + `description` 索引 | 固定注入 system prompt（eager 模式） |
| Agent 决策 | `SKILL.md` 全文 | 调用 `skill_view(name)` tool 时 |
| 深度引用 | `references/`、`scripts/` 等 | 调用 `skill_view(name, file_path)` 时 |
| 用户显式 | 全文 + 激活提示 | 输入 `/skill-name` slash command 时 |

**一句话**：用 tool round-trip 换 token 效率；索引常驻，正文按需。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│  Session Start                                              │
│  ├─ build_skills_system_prompt()  → 只注入 name+description │
│  ├─ scan_skill_commands()         → 注册 /skill-name 映射   │
│  └─ build_preloaded_skills_prompt() → 可选：CLI 预加载全文   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Agent Loop (每轮对话)                                       │
│  Model 看到索引 → 决定调用 skills_list / skill_view         │
│  或用户输入 /deploy-k8s → 直接注入完整 skill 内容            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  On-Demand Load                                             │
│  skill_view(name)              → SKILL.md 全文 + linked_files│
│  skill_view(name, file_path)   → references/scripts 等附属文件│
└─────────────────────────────────────────────────────────────┘
```

### 关键模块（Hermes 源码）

| 模块 | 文件 | 职责 |
|------|------|------|
| Tool 层 | `tools/skills_tool.py` | `skills_list`、`skill_view`、发现与解析 |
| Prompt 构建 | `agent/prompt_builder.py` | `build_skills_system_prompt`、索引缓存 |
| Slash Command | `agent/skill_commands.py` | `/skill-name` 扫描与消息构建 |
| 预处理 | `agent/skill_preprocessing.py` | 模板变量、inline shell |
| 工具函数 | `agent/skill_utils.py` | frontmatter 解析、目录遍历、插件命名空间 |

---

## 3. Progressive Disclosure 分级披露

```
Level 0: system prompt / skills_list()
         → [{name, description, category}, ...]     (~3k tokens，随 skill 数量增长)

Level 1: skill_view(name)
         → SKILL.md 全文 + linked_files 清单        (按需)

Level 2: skill_view(name, file_path)
         → references/templates/scripts 单文件       (更细粒度按需)
```

### 为什么这样设计？

- **Token 成本可控**：100 个 skill 若全量加载可能占满 context；索引只保留「目录」。
- **Agent 自主决策**：LLM 根据任务语义选择是否加载，类似轻量 RAG。
- **用户可强制加载**：`/skill-name` 绕过 LLM 决策，适合明确意图场景。

### Lazy 模式（演进中）

Issue #2045 提议 `skills.loading: lazy`：system prompt **不**注入完整索引，改为提示「需要时调用 `skills_list()`」。适合 skill 数量极大（数百上千）的场景。

---

## 4. 存储与发现机制

### 目录约定

```
~/.hermes/skills/              # 主目录（本地优先，可写）
├── deploy-k8s/
│   ├── SKILL.md               # 必需：YAML frontmatter + Markdown 正文
│   ├── references/
│   ├── templates/
│   ├── scripts/
│   └── assets/
└── mlops/
    └── fine-tuning/
        └── SKILL.md

skills.external_dirs           # config.yaml 配置的额外只读目录
plugin:skill-name              # 插件命名空间（qualified name）
```

### SKILL.md 格式（agentskills.io 兼容）

```yaml
---
name: deploy-k8s
description: Deploy services to Kubernetes...
version: 1.0.0
platforms: [macos, linux]       # 可选：平台过滤
metadata:
  hermes:
    tags: [kubernetes, deploy]
    config:                     # 可从 config.yaml 注入
      api_endpoint: ...
---

# 正文（Markdown）
```

### 发现算法 `_find_all_skills()`

1. 遍历 `~/.hermes/skills/` + `external_dirs`
2. `iter_skill_index_files()` 递归找 `SKILL.md`，跳过 `.git`、`node_modules` 等
3. 只读文件前 **4KB** 解析 frontmatter（索引阶段不读正文）
4. 过滤：`platform`、`environment`、`disabled`、同名去重（本地优先）
5. 返回 `{name, description, category}` 元数据列表

### Skill 定位 `skill_view(name)` 三策略

| 策略 | 示例 | 说明 |
|------|------|------|
| 直接路径 | `mlops/axolotl` | `skills_dir / name / SKILL.md` |
| 递归按目录名 | `axolotl` | 匹配 `**/axolotl/SKILL.md` |
| 遗留 flat | `foo.md` | 非目录式旧格式 |

**同名冲突**：多个候选 → 拒绝加载，要求用完整路径（如 `category/skill-name`）。

---

## 5. 三种加载触发路径

### 路径 A：Agent Tool 调用（最常见）

```
User: "帮我部署到 k8s"
  → LLM 看到 system prompt 索引中有 deploy-k8s
  → LLM 调用 skill_view(name="deploy-k8s")
  → Tool result 追加到 messages
  → LLM 基于 skill 正文继续推理
```

### 路径 B：Slash Command（用户显式）

```
User: "/deploy-k8s use canary"
  → resolve_skill_command_key("/deploy-k8s")
  → skill_view(skill_dir) 加载全文
  → build_skill_invocation_message() 格式化为用户/系统消息
  → 直接注入对话，附带 activation_note
```

### 路径 C：CLI 预加载

```
hermes chat --skill deploy-k8s
  → build_preloaded_skills_prompt(["deploy-k8s"])
  → 会话全程 skill 指导生效（非一次性）
```

---

## 6. Tool 层实现

### `skills_list`

- **输入**：可选 `category` 过滤
- **输出**：JSON `{skills: [{name, description, category}], count, hint}`
- **成本**：只返元数据，不读 SKILL.md 正文

### `skill_view`

- **输入**：`name`（必填）、`file_path`（可选）
- **输出**：JSON `{success, name, content, skill_dir, linked_files, ...}`
- **行为**：
  - 无 `file_path` → 返回 SKILL.md 正文 + `linked_files` 清单
  - 有 `file_path` → 返回单个附属文件内容
- **副作用**：`bump_view` / `bump_use` 统计（Curator 生命周期管理）

### Tool 注册

```python
registry.register(name="skills_list", toolset="skills", handler=...)
registry.register(name="skill_view", toolset="skills", handler=...)
```

Agent loop 收到 `tool_calls` 后 dispatch 到 handler，结果作为 `ToolResultMessage` 追加。

---

## 7. System Prompt 索引构建

`build_skills_system_prompt()` 生成类似：

```markdown
## Skills (mandatory)
Before replying, scan the skills below. If a skill matches...
You MUST load it with skill_view(name) and follow its instructions.

<available_skills>
  general:
    - deploy-k8s: Deploy services to Kubernetes...
    - code-review: Structured code review workflow...
</available_skills>
```

### 两层缓存

1. **内存 LRU**：key = `(skills_dir, external_dirs, tools, toolsets, platform, disabled)`
2. **磁盘 snapshot**：`.skills_prompt_snapshot.json`，用文件 mtime manifest 校验失效

### 条件过滤 `_skill_should_show`

Skill frontmatter 可声明：

- `requires_toolsets` / `requires_tools` — 缺工具则隐藏
- `fallback_for_toolsets` — 主工具可用时隐藏 fallback skill

---

## 8. Slash Command 机制

### 扫描 `scan_skill_commands()`

- 会话启动时扫描所有 skill 的 frontmatter
- `name` 规范化为 `/hyphen-slug`（空格、下划线 → 连字符，去掉非法字符）
- 缓存到 `_skill_commands` 字典

### 消息构建 `build_skill_invocation_message()`

加载后消息包含：

1. **activation_note** — 告知 LLM 必须遵循 skill 指令
2. **SKILL.md 正文**（经预处理）
3. **`[Skill directory: /abs/path]`** — 方便直接跑 scripts
4. **`[Skill config: ...]`** — 从 `config.yaml` 注入的配置值
5. **Supporting files 列表** — 提示用 `skill_view(name, file_path)` 加载
6. **用户附加指令** — slash 后面的文字

### 重载 `/reload-skills`

- 只重扫 slash command 映射
- **不** invalidate system prompt cache（保护 prefix caching）

---

## 9. 预处理与安全

### 加载时预处理 `preprocess_skill_content()`

| 功能 | 语法 | 配置 |
|------|------|------|
| 模板变量 | `${HERMES_SKILL_DIR}`、`${HERMES_SESSION_ID}` | `skills.template_vars: true` |
| Inline shell | `` !`date +%Y-%m-%d` `` | `skills.inline_shell: false`（默认关） |

索引阶段**不做**预处理，只在 `skill_view` / slash 加载时执行。

### 安全机制

| 检查 | 时机 |
|------|------|
| 路径穿越 `..` | `name`、`file_path` 校验 |
| 可信根目录 | skill 必须在 `~/.hermes/skills` 或 `external_dirs` 内 |
| Prompt injection 模式检测 | 加载时 log warning，不阻断 |
| `skill_manage` 写入 | atomic write + security scan，失败 rollback |

### Offer-time vs Load-time 过滤

| 过滤器 | 索引/slash/skills_list | skill_view 显式加载 |
|--------|------------------------|---------------------|
| platform | 隐藏 | 可拒绝 |
| environment (docker/kanban) | 隐藏 | 可 bypass |
| disabled | 隐藏 | 拒绝 |

---

## 10. 缓存与重载策略

```
reload_skills()
  ├─ 重扫磁盘 → 更新 slash_commands
  ├─ 不碰 system prompt LRU / disk snapshot
  └─ 新 skill 立即可用 via /name 或 skill_view

hermes update
  ├─ bundled skills 同步到 ~/.hermes/skills/
  └─ manifest (.bundled_manifest) 记录 origin hash
```

---

## 11. 与 Cursor Skills 对比

| 维度 | Hermes | Cursor |
|------|--------|--------|
| 存储 | `~/.hermes/skills/` 文件系统 | `~/.cursor/skills-cursor/` + rules |
| 发现 | 扫描 + system prompt 索引 | `<agent_skills>` 列 name+description |
| 加载方式 | LLM 调 `skill_view` tool | Agent **Read 工具读 SKILL.md 文件** |
| 用户触发 | `/slash` + CLI `--skill` | 任务相关时自动读 skill |
| 自管理 | `skill_manage` tool | 用户手动维护 |
| Token 策略 | 索引常驻 + 正文按需 | 读文件时一次性进入 context |

**可迁移模式**：若你在自建 Agent 中复用 Hermes 思路，核心是 **「索引 + tool 按需加载」**，而非 **「全量 prompt 注入」**。

---

## 12. 本地 Demo 使用指南

### 目录结构

```
demos/hermes-skill-loader/
├── skill_loader.py      # 核心实现（stdlib only）
├── demo.py              # 交互 / 单轮演示
├── scenario.py          # 完整脚本化 walkthrough（推荐入门）
└── skills/
    ├── deploy-k8s/
    │   ├── SKILL.md
    │   └── references/checklist.md
    └── code-review/
        └── SKILL.md
```

### 推荐学习路径（10 分钟）

```bash
cd demos/hermes-skill-loader

# ① 一键跑通完整生命周期（无需 API Key）
python scenario.py

# ② 理解 eager vs lazy 索引策略
python demo.py --show-index
python demo.py --loading lazy --show-index

# ③ 单轮交互模拟
python demo.py --turn "help me deploy to k8s"
python demo.py --turn "save skill"    # skill_manage create
python demo.py --turn "patch skill"   # skill_manage patch

# ④ 自由 REPL
python demo.py
```

### `scenario.py` 演示的流程

| 步骤 | 模拟的真实行为 |
|------|----------------|
| 1–2 | Session start：eager 索引 vs lazy 单行提示 |
| 3 | Agent 调 `skill_view` 加载已有 skill |
| 4–6 | Agent 调 `skill_manage` 创建、写附属文件、patch |
| 7–9 | 索引刷新 → 加载 agent 自建的 skill + reference |
| 10 | 安全扫描拦截 prompt injection |
| 11 | `/api-migration` slash command 加载 |

场景在 `skills/_sandbox/` 隔离运行，结束后自动清理（`--keep` 可保留）。

### Demo 模拟了什么？

| 真实 Hermes | Demo |
|-------------|------|
| LLM 决定调 tool | `mock_agent_decide()` 关键词规则 / `scenario.py` 脚本 |
| `skill_view` tool | `tool_skill_view()` |
| `skill_manage` tool | `tool_skill_manage()` — create/patch/edit/delete/write_file |
| `skills.loading: lazy` | `loading_mode="lazy"` |
| system prompt 索引 | `build_system_prompt_index()` |
| `/deploy-k8s` | `build_slash_invocation_message()` |
| atomic write + security scan | `atomic_write_text()` + `security_scan_content()` |

### 在代码中集成

```python
from pathlib import Path
from skill_loader import HermesSkillLoader

loader = HermesSkillLoader(Path("skills"), session_id="my-session")

# Tier 0 — eager（默认）或 lazy
system_prompt += loader.build_system_prompt_index()

# Tier 1
catalog_json = loader.tool_skills_list()

# Tier 2
skill_json = loader.tool_skill_view("deploy-k8s")

# Tier 3
ref_json = loader.tool_skill_view("deploy-k8s", file_path="references/checklist.md")

# Agent 自建 skill（procedural memory）
loader.tool_skill_manage("create", name="my-workflow", content="---\nname: my-workflow\n...")
loader.tool_skill_manage("patch", name="my-workflow", old_string="step 1", new_string="step 1 (revised)")

# Slash
msg = loader.build_slash_invocation_message("/deploy-k8s", "use canary")
```

### 扩展练习

1. ~~增加 `skills.loading: lazy` 模式~~ ✅ 已实现
2. ~~增加 `skill_manage(create/patch)`~~ ✅ 已实现
3. 实现磁盘 snapshot 缓存 — 对照 `prompt_builder.py` 的 manifest 校验
4. 把 `mock_agent_decide` 换成真实 LLM + function calling（需 API Key）

---

## 13. 源码对照索引

| 概念 | Hermes 源码位置 | Demo 对应 |
|------|-----------------|-----------|
| 元数据扫描 | `skills_tool._find_all_skills()` | `find_all_skills_metadata()` |
| 目录遍历 | `skill_utils.iter_skill_index_files()` | `iter_skill_index_files()` |
| 列表 tool | `skills_tool.skills_list()` | `tool_skills_list()` |
| 查看 tool | `skills_tool.skill_view()` | `tool_skill_view()` |
| 管理 tool | `tools/skill_manage` | `tool_skill_manage()` |
| Lazy 索引 | `skills.loading: lazy` | `loading_mode="lazy"` |
| Prompt 索引 | `prompt_builder.build_skills_system_prompt()` | `build_system_prompt_index()` |
| 完整场景 | CLI / gateway agent loop | `scenario.py` |
| Slash 扫描 | `skill_commands.scan_skill_commands()` | `scan_skill_commands()` |
| Slash 消息 | `skill_commands.build_skill_invocation_message()` | `build_slash_invocation_message()` |
| 模板替换 | `skill_preprocessing.substitute_template_vars()` | `substitute_template_vars()` |
| Agent 循环 | `cli.py` / `gateway/run.py` | `run_agent_turn()` |

---

## 14. 设计 Checklist

自建 Agent Skill 系统时，可按此清单自检：

### 存储

- [ ] 每个 skill 是目录 + `SKILL.md`（frontmatter + body）
- [ ] 附属文件分 `references/`、`scripts/`、`templates/`、`assets/`
- [ ] 支持多根目录扫描，本地优先于外部

### 披露层级

- [ ] Tier 0：索引只含 name + description
- [ ] Tier 1：tool 按需返回全文
- [ ] Tier 2：tool 按需返回单文件
- [ ] 不在索引阶段读大文件

### 触发

- [ ] Agent 通过 tool 自主加载
- [ ] 用户 slash command 强制加载
- [ ] 可选 CLI 预加载

### 安全

- [ ] 禁止 `..` 和绝对路径
- [ ] 文件必须在可信根内
- [ ] 同名冲突显式报错
- [ ] 写入走 atomic + scan

### 性能

- [ ] 索引有内存/磁盘缓存
- [ ] 重载不破坏 prefix cache（若适用）
- [ ] frontmatter 只读前 N KB

### 可观测

- [ ] 记录 view/use 次数（生命周期管理）
- [ ] 加载失败返回 available_skills hint

---

## 附录：Agent 主循环伪代码

```python
def agent_turn(session, user_message):
    # Slash command 优先处理
    if user_message.startswith("/"):
        skill_msg = build_skill_invocation_message(user_message)
        messages.append(skill_msg)
        # 继续让 LLM 基于 skill 回复
    else:
        messages.append(user_message)

    while True:
        response = llm.chat(
            system=session.system_prompt,   # 含 <available_skills> 索引
            messages=messages,
            tools=["skills_list", "skill_view", ...],
        )

        if not response.tool_calls:
            return response.text

        for call in response.tool_calls:
            result = dispatch_tool(call.name, call.args)
            messages.append(ToolResult(call.id, result))
        # loop — LLM 可能继续调 tool 或输出最终回复
```

---

*文档与 Demo 基于 Hermes Agent 开源实现提炼，已脱敏，适用于通用 Agent Skill 系统设计学习。*
