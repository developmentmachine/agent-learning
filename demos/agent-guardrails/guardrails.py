import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

class GuardrailException(Exception):
    """当触发护栏拦截时抛出的异常"""
    pass

class AgentGuardrails:
    """
    Agent 护栏系统：负责在执行前、执行中、执行后进行安全与成本校验。
    """
    def __init__(self, 
                 max_tokens_all_sessions: int = 50000,
                 sensitive_tools: list = None):
        self.max_tokens = max_tokens_all_sessions
        self.used_tokens = 0
        self.sensitive_tools = sensitive_tools or []

    def verify_input(self, user_input: str):
        """
        [输入护栏]：检查恶意注入或敏感词。
        """
        # 简单模拟提示词注入拦截
        danger_keywords = ["ignore previous instructions", "system root", "rm -rf"]
        for word in danger_keywords:
            if word in user_input.lower():
                raise GuardrailException(f"⚠️ [Input Guardrail] Detected potentially malicious input: '{word}'")
        return True

    def verify_action(self, tool_name: str, args: dict):
        """
        [执行护栏]：权限校验与人类在环 (HITL)。
        """
        if tool_name in self.sensitive_tools:
            print(f"\n🚨 [HITL Required] Agent 尝试执行敏感操作: {tool_name}({args})")
            user_confirm = input("❓ 您是否批准此操作? (yes/no): ").strip().lower()
            if user_confirm != "yes":
                raise GuardrailException(f"🚫 [Action Guardrail] User REJECTED the sensitive tool call: {tool_name}")
        return True

    def track_resources(self, prompt_tokens: int, completion_tokens: int):
        """
        [资源护栏]：监控并限制 Token 消耗。
        """
        total = prompt_tokens + completion_tokens
        self.used_tokens += total
        logging.info(f"📊 [Resource Tracker] Tokens used in this turn: {total}. Total session: {self.used_tokens}/{self.max_tokens}")
        
        if self.used_tokens > self.max_tokens:
            raise GuardrailException("💸 [Budget Guardrail] Token limit exceeded! Stopping for cost safety.")

    def verify_output(self, llm_output: str):
        """
        [输出护栏]：内容合规性检查。
        """
        banned_words = ["confidential_password", "internal_ip_10.0.0.1"]
        for word in banned_words:
            if word in llm_output:
                return f"[Output Filtered] The response contained restricted information ('{word}')."
        return llm_output
