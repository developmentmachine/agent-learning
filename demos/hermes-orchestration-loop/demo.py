import time
from orchestrator import Orchestrator

# --- 模拟工具库 ---

def read_file(path: str):
    """模拟文件读取工具，包含一个故意的错误逻辑"""
    if path == "user_data.txt":
        return "Content: {'name': 'Alice', 'role': 'admin'}"
    else:
        # 模拟文件不存在报错
        raise FileNotFoundError(f"File '{path}' does not exist on this system.")

def write_report(content: str):
    """模拟写入报告"""
    return "Successfully wrote report to disk."

# --- 模拟 LLM 大脑 ---
# 这里模拟了一个会“犯错”但在收到报错后能“纠正”的大脑

def mock_llm_logic(history: list) -> str:
    # 获取最后一条消息
    last_msg = history[-1]["content"]
    
    # 逻辑 1：第一轮，大脑决定读取一个错误的文件名
    if "find out who is the admin" in last_msg.lower():
        return """Thought: I need to find the user data to identify the admin. I'll check 'users.json' first.
```json
{
  "tool": "read_file",
  "args": {"path": "users.json"}
}
```"""

    # 逻辑 2：如果收到“文件不存在”的报错，大脑进行自我纠正 (Self-Correction)
    if "FileNotFoundError" in last_msg or "does not exist" in last_msg:
        return """Thought: It seems 'users.json' does not exist. I might have remembered the filename incorrectly. Let me try 'user_data.txt' instead, which is a common naming pattern.
```json
{
  "tool": "read_file",
  "args": {"path": "user_data.txt"}
}
```"""

    # 逻辑 3：如果读取成功，给出最终答案
    if "Alice" in last_msg:
        return "Thought: I have the data now. Alice is the admin.\nFinal Answer: The admin is Alice."

    return "Thought: I am unsure what to do next."

# --- 执行 Demo ---

def main():
    print("=== Agent Core Reasoning & Self-Correction Demo ===\n")
    
    # 初始化工具
    available_tools = {
        "read_file": read_file,
        "write_report": write_report
    }

    # 初始化编排引擎
    agent = Orchestrator(
        llm_client=mock_llm_logic,
        tools=available_tools,
        max_steps=5
    )

    # 下达一个需要多步推理和容错的任务
    trace = agent.run("Please find out who is the admin in our system.")

    print("\n" + "="*50)
    print("📋 [Full Reasoning Trace Summary]")
    for i, step in enumerate(trace):
        role = step['role'].upper()
        content = step['content'][:100].replace('\n', ' ') + "..." if len(step['content']) > 100 else step['content']
        print(f"[{i}] {role}: {content}")

if __name__ == "__main__":
    main()
