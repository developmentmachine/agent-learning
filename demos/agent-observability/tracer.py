import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List

class AgentTracer:
    """
    企业级追踪器：负责收集、结构化并在本地记录 Agent 的执行全链路。
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.trace_id = str(uuid.uuid4())
        self.spans: List[Dict] = []
        self.start_time = time.time()

    def start_span(self, name: str, type: str, input_data: Any = None):
        """开始一个子任务追踪 (如 LLM 调用或工具执行)"""
        span = {
            "span_id": str(uuid.uuid4()),
            "name": name,
            "type": type,
            "start_time": datetime.now().isoformat(),
            "input": input_data,
            "status": "running"
        }
        self.spans.append(span)
        return span["span_id"]

    def end_span(self, span_id: str, output_data: Any = None, metadata: Dict = None):
        """结束子任务追踪"""
        for span in self.spans:
            if span["span_id"] == span_id:
                span["end_time"] = datetime.now().isoformat()
                span["output"] = output_data
                span["metadata"] = metadata or {}
                span["status"] = "success"
                # 计算耗时 (简单模拟)
                span["latency_ms"] = round((time.time() - self.start_time) * 1000, 2)
                break

    def get_full_trace(self) -> Dict:
        """生成最终的结构化 Trace 报告"""
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "total_latency_ms": round((time.time() - self.start_time) * 1000, 2),
            "steps": self.spans
        }

    def export_to_json(self, file_path: str):
        """导出为 JSON 文件，用于后续审计或看板展示"""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.get_full_trace(), f, indent=2, ensure_ascii=False)
        print(f"💾 [Trace Exported]: {file_path}")
