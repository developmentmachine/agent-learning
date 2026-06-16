import time
import logging
from session_manager import AdvancedSessionManager, SQLiteDBManagerMock

def mock_llm_api_call(payload: list, mock_response: dict) -> dict:
    """模拟大模型 API 调用并返回预设的结果"""
    print("\n" + "="*60)
    print("🚀 [LLM API 调用] 发送 Payload (享受 Prefix Cache 加速)...")
    for msg in payload:
        role = msg['role'].upper()
        content = msg['content'][:80].replace('\n', ' ') + "..." if len(msg['content']) > 80 else msg['content']
        print(f"  [{role}] {content}")
    print("="*60 + "\n")
    time.sleep(1) # 模拟网络延迟
    return mock_response

def main():
    print("=== Advanced Hermes Session Management Demo ===\n")
    
    # 模拟之前 Session 存在数据库中的历史记录
    global_db = SQLiteDBManagerMock()
    global_db.storage.append({"session_id": "old_sess_1", "role": "user", "content": "I setup a redis cluster yesterday."})
    
    # --- 启动新 Session ---
    session = AdvancedSessionManager(session_id="sess_current")
    session.db = global_db # 共享全局 DB 模拟
    
    # 场景 1：分级披露 (Progressive Disclosure)
    print(">>> USER: How do I deploy the app to k8s?")
    session.add_user_message("How do I deploy the app to k8s?")
    
    # 模型看到 System Prompt 里的索引，决定调用 read_skill_detail
    mock_resp_1 = {
        "text": "I need to check the exact procedure for k8s deployment.",
        "tool_calls": [{"name": "read_skill_detail", "arguments": {"skill_name": "deploy-k8s"}}]
    }
    payload = session.get_payload_for_llm()
    resp1 = mock_llm_api_call(payload, mock_resp_1)
    session.add_model_message(resp1["text"], tool_calls=resp1["tool_calls"])
    
    # Agent 执行工具，拉取详情注入上下文
    print(f">>> TOOL EXECUTED: read_skill_detail('deploy-k8s')")
    skill_content = session.memory.read_skill_detail("deploy-k8s")
    session.add_tool_message("read_skill_detail", skill_content)
    
    # 模型基于拉取到的详情回答
    mock_resp_2 = {"text": "To deploy to k8s, follow these steps: 1. kubectl apply... 2. verify pods..."}
    payload = session.get_payload_for_llm()
    resp2 = mock_llm_api_call(payload, mock_resp_2)
    session.add_model_message(resp2["text"])
    print(f">>> AGENT: {resp2['text']}\n")

    # 场景 2：基于本地 DB 的自主检索
    print(">>> USER: Do you remember what database I setup yesterday?")
    session.add_user_message("Do you remember what database I setup yesterday?")
    
    # 模型没有在当前上下文中找到，决定搜索数据库
    mock_resp_3 = {
        "text": "Let me search my database for your recent activities.",
        "tool_calls": [{"name": "session_search", "arguments": {"query": "setup yesterday"}}]
    }
    payload = session.get_payload_for_llm()
    resp3 = mock_llm_api_call(payload, mock_resp_3)
    session.add_model_message(resp3["text"], tool_calls=resp3["tool_calls"])
    
    # Agent 执行数据库搜索
    print(f">>> TOOL EXECUTED: session_search('setup yesterday')")
    search_result = session.db.search("setup yesterday")
    session.add_tool_message("session_search", search_result)
    
    # 模型基于搜索结果回答
    mock_resp_4 = {"text": "Yes, I searched the historical logs. You set up a Redis cluster yesterday."}
    payload = session.get_payload_for_llm()
    resp4 = mock_llm_api_call(payload, mock_resp_4)
    session.add_model_message(resp4["text"])
    print(f">>> AGENT: {resp4['text']}\n")

    # 场景 3：后台复盘 (Background Review)
    print(">>> USER: Actually, I am building a React frontend for it.")
    session.add_user_message("Actually, I am building a React frontend for it.")
    session.add_model_message("That's great! React pairs well with your stack.")
    print(f">>> AGENT: That's great! React pairs well with your stack.\n")
    
    print(">>> Session Ends. Triggering Background Review...")
    # 用户交互结束，触发后台复盘
    session.trigger_background_review()
    
    # 主线程继续执行，证明无阻塞
    print(">>> Main thread is free to close or handle new user input immediately.")
    time.sleep(3) # 等待后台线程打印日志以便观察
    print(">>> Demo Finished.")

if __name__ == "__main__":
    main()
