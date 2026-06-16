# Agent Evaluation & Benchmarking

在 Agent 工程化落地中，**“如何保证迭代是往好的方向发展，而不是往坏的方向发展”** 是一个核心难题。Prompt 的微调、Tool 的增删、逻辑架构（如 Memory 或 Skill 加载机制）的改变，都可能导致 Agent 在某些场景下表现提升，而在另一些场景下发生“灾难性遗忘”或表现倒退。

引入系统的 **Benchmark（基准测试）** 与 **Evaluation（评估，简称 Eval）** 机制，是 Agent 从“玩具”走向“工程化”的必经之路。

---

## 1. Benchmark 与 Eval 的区别与联系

虽然这两个词经常混用，但在 Agent 开发生命周期中，它们有不同的侧重点：

### Benchmark（基准测试）
- **定义**：行业内公认的、标准化的测试集。用于衡量你的 Agent（或底层基座模型）在一般性任务上的基础能力。
- **作用**：横向对比（我的 Agent 比开源的通用 Agent 强还是弱？大模型选 GPT-4 还是 Claude 3.5 Sonnet？）。
- **代表项目**：
  - **Coding 类**：[SWE-bench](https://www.swebench.com/)（解决真实的 GitHub Issue）、HumanEval。
  - **Web/操作类**：[WebArena](https://webarena.dev/)、OSWorld。
  - **推理/通用类**：AgentBench。

### Evaluation / Evals（内部评估集）
- **定义**：针对**你自己业务场景**构建的定制化测试用例与评分机制。
- **作用**：纵向对比（今天提交的 PR，有没有把昨天修复的 Bug 又改坏了？新加的 Skill 有没有干扰旧的 Skill？）。
- **特点**：它是 Agent 开发的“单元测试”和“集成测试”。

---

## 2. 为什么需要构建 Eval 系统？

1. **防退化（Regression Prevention）**：大模型的输出具有非确定性，仅仅修改了 System Prompt 的一句话，可能导致 Agent 突然忘记调用某个关键 Tool。Eval 可以在代码合并前拦截这种退化。
2. **量化迭代 ROI**：当你花了三天时间优化“Memory 召回”逻辑，你怎么向团队证明这三天的工作是有价值的？你需要一组数字：比如“在 50 个高频场景下，任务成功率从 72% 提升到了 85%”。
3. **数据驱动的 Prompt Engineering**：拍脑袋改 Prompt 往往是拆东墙补西墙。有了 Eval，Prompt 的修改变成了一个类似模型训练的“求导”过程——朝着 Eval 分数更高的方向优化。

---

## 3. Agent Eval 的三种核心范式

### 3.1 基于结果的确定性评估（Deterministic / Rule-based）
这是最基础、最可靠的 Eval 方式，类似于传统的自动化测试。
- **怎么做**：给定一个任务，看 Agent 能否达到特定的状态。
- **例子**：
  - 任务：“帮我修复 `demo.py` 里第 45 行的数组越界报错。”
  - 评估规则：运行 `pytest`，如果所有测试通过，得 1 分；否则 0 分。
  - 任务：“查询昨天数据库里新增了多少用户。”
  - 评估规则：检查 Agent 最后输出的 JSON 中 `user_count` 字段是否等于已知答案 `142`。

### 3.2 基于过程的轨迹评估（Trajectory Evaluation）
Agent 完成任务的过程往往涉及多步循环（ReAct、Plan & Execute）。只看最终结果是不够的，还要看过程是否合理、有没有绕弯路。
- **评估维度**：
  - **Tool 调用准确率**：是否调用了预期中的 Tool？参数是否正确？
  - **效率（Steps / Token 消耗）**：解决同一个问题，旧版本用了 10 步，新版本用了 5 步，说明新版本更聪明。
  - **错误恢复（Self-Correction）**：当 Tool 报错时，Agent 是陷入死循环，还是能够阅读错误信息并修正？

### 3.3 LLM-as-a-Judge（大模型裁判）
对于没有绝对标准答案的主观任务（例如：“帮我写一份代码评审（Code Review）”），规则评估无能为力。此时引入一个更强大的 LLM（如 GPT-4o 或 Claude 3.5 Sonnet）来做裁判。
- **怎么做**：将 Agent 的回答、标准参考答案（Golden Answer）、评分标准（Rubric）一起喂给裁判大模型，让它打分（1-5分）并给出理由。
- **注意事项**：裁判模型会有位置偏见（Position Bias）和长度偏见（倾向于给字数多的打高分），需要通过技巧（如交换对比顺序、严格限制评分维度）来校准。

---

## 4. 如何从零搭建业务 Agent 的 Eval 系统？

### 第一步：积累“黄金数据集”（Golden Dataset）
- 永远不要一开始就追求 1000 个测试用例。从 **20-50 个最具代表性的业务请求**开始。
- 来源：真实的线上 User Prompt，人工标注出“理想的最终状态”或“必须调用的核心工具”。

### 第二步：自动化执行管道（Eval Pipeline）
- 构建一个沙盒环境（Sandbox）：Docker 容器或临时工作区。
- 脚本化执行：对于数据集中的每个 Case，初始化沙盒 -> 唤醒 Agent 接受任务 -> 等待 Agent 结束 -> 收集执行结果。
- **工具推荐**：目前有很多开源 Eval 框架，如 **LangSmith**、**Phoenix (Arize)**、**Ragas** 或 OpenAI 官方的 **Evals** 库。

### 第三步：定义核心指标并整合进 CI/CD
- **指标卡片**：
  - Pass Rate（任务成功率）
  - Average Turn Count（平均交互轮数）
  - Tool Hallucination Rate（工具幻觉/乱用率）
- **CI 拦截**：在 GitHub Actions 中，每次修改 Prompt 或 Agent 核心逻辑的 PR，必须触发 Eval 跑一遍黄金数据集，成功率下降超过 5% 即 Block PR。

---

## 5. 持续学习与反馈闭环（Online Evals）

离线测试集的局限性在于永远无法覆盖真实的边缘场景。因此，真正的成熟体系必须包含**线上评估（Online Evals）**：

1. **用户隐式反馈**：
   - 比如代码补全场景下，用户的 Acceptance Rate（采纳率）。
   - 聊天场景下，用户是否按下了 👎（Thumbs down），或者在两轮对话内放弃了当前会话。
2. **异步巡检（Background Review）**：
   - 即 `hermes-closed-loop-learning.md` 中提到的理念。后台跑一个 Curator 守护进程，异步拉取线上的 Agent 交互记录（Trace），使用 LLM-as-a-Judge 打分。
   - 发现表现差的 Case，由人工 Review 后沉淀为新的 **Offline Eval 测例** 或提取为 **Skill/Memory** 反哺给 Agent。

---

## 6. 学习路线建议

如果你准备在这个方向深入，推荐以下学习路径：

1. **基础认知**：阅读 [SWE-bench 论文与实现](https://github.com/princeton-nlp/SWE-bench)，理解学术界是如何构造高难度、基于环境状态验证的 Benchmark 的。
2. **工具熟悉**：挑选一个 Eval 框架（如 LangSmith 或 Langfuse），跑通一个最小的打分 Demo，体验 Trace 的录制与 LLM-as-a-Judge。
3. **动手实践**：在本项目新增的 `demos/agent-evaluation/` 目录下，尝试针对前面的 `hermes-skill-loader` 写一个简单的批量测试脚本，验证“传入不同输入时，它是否能够准确命中对应的 Skill”。
