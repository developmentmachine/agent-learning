import time
import os
from tracer import AgentTracer

def main():
    print("=== Enterprise Agent Observability Demo ===\n")
    
    # 1. 开启一个追踪会话
    tracer = AgentTracer(session_id="user_123_project_abc")
    print(f"📡 [Tracing Started] Trace ID: {tracer.trace_id}")

    # --- 模拟执行流程 ---

    # 步骤 1: 内存检索
    s1 = tracer.start_span("Memory Recall", type="retrieval", input_data="context for auth bug")
    time.sleep(0.3) # 模拟耗时
    tracer.end_span(s1, output_data="Found previous fix in PR-456", metadata={"index": "vector_db_v2"})

    # 步骤 2: LLM 推理 (Thought + Action)
    s2 = tracer.start_span("LLM Reasoning", type="llm_call", input_data="User query: fix auth bug")
    time.sleep(1.2)
    llm_decision = {"thought": "I need to read auth.py", "tool": "read_file", "args": {"path": "auth.py"}}
    tracer.end_span(s2, output_data=llm_decision, metadata={"model": "gemini-1.5-pro", "tokens": 850})

    # 步骤 3: 工具执行
    s3 = tracer.start_span("Tool Execution", type="action", input_data=llm_decision["args"])
    time.sleep(0.5)
    tool_result = "def login(): ... # BUG: missing salt"
    tracer.end_span(s3, output_data=tool_result, metadata={"exit_code": 0})

    # 步骤 4: 最终回复
    s4 = tracer.start_span("Final Synthesis", type="llm_call")
    time.sleep(0.8)
    final_ans = "The bug is in line 45 of auth.py. I've found the root cause."
    tracer.end_span(s4, output_data=final_ans, metadata={"tokens": 1200})

    print("\n✅ Task completed. Generating Audit Log...")

    # 2. 导出 Trace 文件
    trace_file = "agent_execution_trace.json"
    tracer.export_to_json(trace_file)

    # 3. 打印分析
    report = tracer.get_full_trace()
    print("\n--- 🔍 Trace Analysis Report ---")
    print(f"Total Steps: {len(report['steps'])}")
    print(f"Total Latency: {report['total_latency_ms']} ms")
    
    print("\nStep breakdown:")
    for step in report['steps']:
        print(f"  - {step['name']} ({step['type']}): {step['latency_ms']}ms")

if __name__ == "__main__":
    main()
