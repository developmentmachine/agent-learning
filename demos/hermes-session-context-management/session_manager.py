import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

@dataclass
class Message:
    """表示对话中的单条消息"""
    role: str  # 'system', 'user', 'model', 'tool'
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "content": self.content}

class SQLiteDBManagerMock:
    """
    模拟底层的 SQLite + FTS5 数据库。
    用于持久化存储所有历史 Session 的流水账。
    """
    def __init__(self):
        self.storage = []
        
    def save_message(self, session_id: str, msg: Message):
        # 实际这里会执行 INSERT INTO messages ...
        self.storage.append({"session_id": session_id, "role": msg.role, "content": msg.content})
        
    def search(self, query: str) -> str:
        """模拟 FTS5 全文检索"""
        results = [m for m in self.storage if query.lower() in m['content'].lower()]
        if not results:
            return "No historical records found."
        return json.dumps(results[:3], ensure_ascii=False)  # 返回最相关的3条

class MemoryManager:
    """
    双轨记忆系统 (Dual-Track Memory) 管理器
    """
    def __init__(self):
        # 声明式记忆 (事实类) - 启动时全量加载
        self.declarative_memory = "USER_PREF: prefers Python.\nPROJECT_RULE: main branch is 'master'."
        
        # 程序式记忆 (流程类/Skills) - 分级披露，仅提供索引
        self.procedural_skills_index = {
            "deploy-k8s": "How to deploy to Kubernetes.",
            "fix-bug": "Standard debugging procedure."
        }
        
        # 完整的程序式记忆 (模拟存在本地 Markdown 文件中)
        self.procedural_skills_detail = {
            "deploy-k8s": "Step 1: kubectl apply. Step 2: verify pods.",
            "fix-bug": "Step 1: Check logs using `grep`. Step 2: Read source file. Step 3: Write test."
        }

    def get_frozen_system_prompt(self) -> str:
        """生成冻结的 System Prompt 快照 (Prefix Cache)"""
        prompt = "You are an advanced Agent.\n\n[DECLARATIVE MEMORY]\n" + self.declarative_memory + "\n\n"
        prompt += "[AVAILABLE SKILLS INDEX]\n"
        for name, desc in self.procedural_skills_index.items():
            prompt += f"- {name}: {desc}\n"
        prompt += "\nUse tools to fetch full skill details or search past conversations."
        return prompt
        
    def read_skill_detail(self, skill_name: str) -> str:
        """按需加载工具 (Progressive Disclosure)"""
        return self.procedural_skills_detail.get(skill_name, "Skill not found.")

def background_review_task(conversation_snapshot: List[Dict]):
    """
    Background Review (后台复盘机制) - 守护线程执行
    """
    logging.info("[Background Daemon] Started review of recent conversation...")
    time.sleep(2) # 模拟大模型复盘的思考时间
    
    # 模拟发现新知识
    new_knowledge_found = False
    for msg in conversation_snapshot:
        if "React" in msg.get("content", ""):
            new_knowledge_found = True
            
    if new_knowledge_found:
        logging.info("[Background Daemon] Found new preference: User works with React. Updating MEMORY.md (will take effect next session).")
    else:
        logging.info("[Background Daemon] No new significant information to consolidate.")

class AdvancedSessionManager:
    """
    高级 Session 管理器，集成冻结 System Prompt、数据库持久化和后台复盘。
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history: List[Message] = []
        
        # 初始化组件
        self.db = SQLiteDBManagerMock()
        self.memory = MemoryManager()
        
        # 1. 获取并冻结 System Prompt 快照 (利用 Prefix Cache)
        frozen_prompt = self.memory.get_frozen_system_prompt()
        self.system_message = Message(role="system", content=frozen_prompt)
        logging.info(f"Session {session_id} initialized with frozen System Prompt (Length: {len(frozen_prompt)} chars).")

    def _append_and_persist(self, msg: Message):
        self.history.append(msg)
        self.db.save_message(self.session_id, msg)

    def add_user_message(self, text: str):
        self._append_and_persist(Message(role="user", content=text))

    def add_model_message(self, text: str, tool_calls: Optional[List[Dict]] = None):
        meta = {"tool_calls": tool_calls} if tool_calls else {}
        self._append_and_persist(Message(role="model", content=text, metadata=meta))

    def add_tool_message(self, tool_name: str, result: str):
        self._append_and_persist(Message(role="tool", content=result, metadata={"tool_name": tool_name}))

    def get_payload_for_llm(self) -> List[Dict[str, Any]]:
        # 实际开发中这里还需要加上 _prune_history_if_needed 逻辑
        payload = [self.system_message.to_dict()]
        for msg in self.history:
            payload.append(msg.to_dict())
            if msg.metadata.get("tool_calls"):
                payload[-1]["tool_calls"] = msg.metadata["tool_calls"]
            if msg.metadata.get("tool_name"):
                payload[-1]["name"] = msg.metadata["tool_name"]
        return payload

    def trigger_background_review(self):
        """触发后台复盘机制"""
        snapshot = [msg.to_dict() for msg in self.history]
        # 启动守护线程，不阻塞主线程回复用户
        t = threading.Thread(target=background_review_task, args=(snapshot,), daemon=True)
        t.start()
