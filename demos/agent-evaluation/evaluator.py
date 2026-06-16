import json
import random
from typing import List, Dict, Any

class Trace:
    """
    Represents the execution trajectory of an Agent.
    Contains the input, a list of steps (thoughts, tool calls), and the final output.
    """
    def __init__(self, prompt: str, steps: List[Dict], final_output: str, tokens_used: int = 0):
        self.prompt = prompt
        self.steps = steps
        self.final_output = final_output
        self.tokens_used = tokens_used

class DeterministicEvaluator:
    """
    1. 确定性评分器 (Deterministic Evaluator)
    Fast, cheap, objective. Uses hardcoded rules to evaluate the Trace.
    """
    @staticmethod
    def evaluate_tool_usage(trace: Trace, required_tool: str) -> bool:
        """检查 Agent 是否在执行过程中调用了某个必须的工具"""
        for step in trace.steps:
            if step.get("type") == "tool_call" and step.get("tool_name") == required_tool:
                return True
        return False

    @staticmethod
    def evaluate_output_keyword(trace: Trace, keyword: str) -> bool:
        """检查最终输出中是否包含指定的关键字"""
        return keyword.lower() in trace.final_output.lower()

class RubricEvaluator:
    """
    2. 模型评分器 (Rubric Evaluator / LLM-as-Judge)
    Flexible, handles qualitative outputs that are hard to code.
    Requires an LLM call in reality.
    """
    def __init__(self, model_name: str = "gemini-1.5-pro"):
        self.model_name = model_name

    def evaluate_reasoning_quality(self, trace: Trace) -> Dict[str, Any]:
        """
        Mock implementation of an LLM-as-Judge evaluating the chain of thought.
        In reality, you would build a prompt with the trace steps and ask the LLM to output JSON.
        """
        # 伪代码：向 LLM 发送带有 JSON Schema 约束的 Prompt 
        # prompt = f"Evaluate the reasoning in this trace: {trace.steps}. Schema: {{'score': 1-10, 'reason': '...'}}"
        
        # 模拟打分
        has_thought = any(s.get("type") == "thought" for s in trace.steps)
        if has_thought:
            return {"score": 9, "reason": "Clear logical reasoning before tool execution.", "passed": True}
        else:
            return {"score": 4, "reason": "Jumped directly to execution without planning.", "passed": False}

class AgentEvaluatorPipeline:
    """
    将所有评分器组合，并支持多次试验 (Trials) 以计算 pass@k 和 pass^k
    """
    def __init__(self):
        self.rubric_evaluator = RubricEvaluator()

    def run_single_eval(self, trace: Trace) -> Dict[str, bool]:
        """单次试验的综合打分"""
        results = {
            "used_required_tool": DeterministicEvaluator.evaluate_tool_usage(trace, "mcp_read_file"),
            "has_success_keyword": DeterministicEvaluator.evaluate_output_keyword(trace, "success"),
            "reasoning_quality": self.rubric_evaluator.evaluate_reasoning_quality(trace)["passed"]
        }
        # 综合判定：所有子项都通过才算这次 trial 成功
        results["trial_passed"] = all(results.values())
        return results

    def calculate_metrics(self, traces: List[Trace]) -> Dict[str, Any]:
        """计算 pass@k 和 pass^k"""
        k = len(traces)
        if k == 0:
            return {}
            
        trial_results = [self.run_single_eval(t)["trial_passed"] for t in traces]
        
        pass_at_k = any(trial_results) # 至少一次成功 (峰值能力)
        pass_caret_k = all(trial_results) # 每次都成功 (稳定性)
        success_rate = sum(trial_results) / k
        
        return {
            "trials_run": k,
            "success_rate": f"{success_rate*100:.1f}%",
            "pass@k": pass_at_k,
            "pass^k": pass_caret_k
        }

# --- Demo Execution ---
if __name__ == "__main__":
    print("=== Agent Evaluation: Hybrid Scoring & Metrics ===")
    
    # 模拟 Agent 对同一个任务执行了 5 次 (由于其非确定性，每次 Trace 略有不同)
    mock_traces = [
        Trace(
            prompt="Read config.json and return its status.",
            steps=[{"type": "thought", "text": "I should read the file."}, {"type": "tool_call", "tool_name": "mcp_read_file"}],
            final_output="Read success!"
        ),
        Trace(
            prompt="Read config.json and return its status.",
            steps=[{"type": "tool_call", "tool_name": "mcp_read_file"}], # 缺失 thought，鲁棒性差
            final_output="Success."
        ),
        Trace(
            prompt="Read config.json and return its status.",
            steps=[{"type": "thought", "text": "Reading..."}, {"type": "tool_call", "tool_name": "mcp_read_file"}],
            final_output="Operation success."
        )
    ]
    
    pipeline = AgentEvaluatorPipeline()
    metrics = pipeline.calculate_metrics(mock_traces)
    
    print(json.dumps(metrics, indent=2))
    print("\n解释:")
    print("- pass@k 为 True 说明 Agent 有能力完成该任务（峰值能力）。")
    print("- pass^k 为 False 说明 Agent 表现不稳定，比如有时缺乏思考过程，导致了部分 Trial 失败（不够鲁棒）。")
