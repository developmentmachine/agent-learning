# Agent 核心编排：推理循环 (Reasoning Loop) 与自我纠正 (Self-Correction)

如果说 Session 管理是 Agent 的“记忆”，工具加载是 Agent 的“技能”，那么**编排循环（Orchestration Loop）**就是 Agent 的“心脏”和“大脑执行引擎”。

自研 Agent 的核心门槛不在于如何调用 API，而在于如何在一个不确定的环境中，通过**循环推理**和**错误处理**完成任务。

---

## 1. 推理范式：ReAct (Reason + Act)

在自研 Agent 时，最推荐的推理范式是 **ReAct**。它强制模型在执行任何操作前先进行“思考”。

一个典型的 ReAct 回合如下：
1.  **Thought (思考)**：模型分析当前状态，决定下一步该做什么。
2.  **Action (行动)**：模型决定调用哪个工具，并给出参数。
3.  **Observation (观察)**：Agent 执行工具，并将结果（成功或报错）返回给模型。
4.  **Repeat**：回到步骤 1，直到模型认为任务已完成。

### 为什么 Thought 如此重要？
没有 Thought 的 Agent 是“盲目”的。Thought 就像是模型的“工作草稿（Scratchpad）”，它能显著降低模型产生幻觉的概率，并让调试（Debugging）变得容易——你可以通过 Trace 清楚地看到模型在哪个环节想歪了。

---

## 2. 自我纠正机制 (Self-Correction)

在现实中，Agent 经常会遇到以下挫折：
- 工具调用参数写错了（JSON 格式错误）。
- 尝试访问的文件不存在（File Not Found）。
- 命令执行超时。

**平庸的 Agent**：直接把报错抛给用户，或者陷入死循环。
**优秀的 Agent**：将 Error 信息封装成 `Observation` 重新喂给模型。

**自研要点**：
不要在框架层拦截所有错误。你应该把 `stderr` 或 `Exception` 转化为一条正常的 `role: tool` 消息。
> **例子**：
> - **Action**: `read_file(path="config.json")`
> - **Observation**: `Error: config.json not found. Did you mean config.yaml?`
> - **Next Thought**: `Oh, I made a mistake. Let me search for yaml files instead.`

---

## 3. 核心循环的生命周期 (Lifecycle)

一个成熟的 Orchestrator 需要管理以下阶段：

1.  **Input Parsing (解析)**：将模型的文本输出（通常包含 Markdown 代码块）解析为结构化的 `ToolCall` 对象。
2.  **Execution (执行)**：调用本地函数或远程 API。
3.  **Error Handling (容错)**：捕获执行异常，并将其格式化为模型可理解的反馈。
4.  **Token Budgeting (预算控制)**：监控循环次数（Max Steps）和 Token 消耗。如果循环了 10 次还没出结果，必须强制停止（Stop Loss），防止死循环导致巨额账单。
5.  **Termination (终止)**：识别模型输出的“任务完成”标识（如 `Final Answer` 或 `<FINISH>` 标签）。

---

## 4. 总结与建议

自研 Agent 理论落地的核心公式：
**`Agent = (LLM + System Prompt) + While-Loop(Parser + Error_Catcher + Max_Steps)`**

在开发时，请务必关注：
- **Trace 的可见性**：确保每一轮的 Thought、Action、Observation 都能被记录和展示。
- **重试的逻辑**：给模型重试的机会，但要限制次数。

（*配套的代码 Demo 位于 `demos/hermes-orchestration-loop` 目录中，展示了一个具备自我纠正能力的智能体执行引擎*）
