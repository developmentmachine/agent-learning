import json
import logging
import re
from typing import List, Dict, Any, Callable, Optional

logging.basicConfig(level=logging.INFO, format="%(message)s")

class Orchestrator:
    """
    Agent 的核心执行引擎 (大脑)。
    负责运行 While 循环、解析模型指令、执行工具、以及处理错误（自我纠正）。
    """
    def __init__(self, 
                 llm_client: Callable, 
                 tools: Dict[str, Callable], 
                 max_steps: int = 5):
        self.llm_client = llm_client # 模拟的 LLM 调用函数
        self.tools = tools           # 可用的工具库
        self.max_steps = max_steps   # 防止死循环的硬限制
        self.history = []            # 本次任务的推理轨迹 (Trace)

    def _parse_action(self, llm_output: str) -> Optional[Dict]:
        """
        解析逻辑：从模型的回复中提取工具调用指令。
        通常建议模型使用特定的格式，如 JSON 代码块。
        """
        # 简单示例：正则提取 ```json ... ``` 中的内容
        match = re.search(r"```json\s*(.*?)\s*```", llm_output, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                return {"error": "Invalid JSON format in Action block"}
        return None

    def run(self, user_goal: str):
        """
        核心推理循环 (Reasoning Loop)
        """
        print(f"\n🎯 [Goal]: {user_goal}")
        self.history.append({"role": "user", "content": user_goal})
        
        current_step = 0
        while current_step < self.max_steps:
            current_step += 1
            print(f"\n--- 🔄 Step {current_step} ---")
            
            # 1. 询问大脑 (LLM) 下一步该做什么
            # 大脑会输出：Thought (思考) + Action (行动指令)
            llm_response = self.llm_client(self.history)
            print(f"🤔 [Thought/Output]:\n{llm_response}")
            self.history.append({"role": "model", "content": llm_response})

            # 检查模型是否认为已经完成了任务
            if "Final Answer:" in llm_response or "任务完成" in llm_response:
                print("\n✅ [Task Finished]")
                break

            # 2. 解析行动指令
            action_req = self._parse_action(llm_response)
            
            if not action_req:
                # 模型输出了文字但没调工具，也没说结束。
                # 这种情况通常需要追加一个提示让模型继续。
                self.history.append({"role": "user", "content": "Please continue or provide a final answer."})
                continue

            if "error" in action_req:
                observation = f"System Error: {action_req['error']}. Please correct your JSON format."
            else:
                # 3. 执行工具并捕获 Observation
                tool_name = action_req.get("tool")
                args = action_req.get("args", {})
                
                print(f"🛠️ [Executing Tool]: {tool_name}({args})")
                
                if tool_name in self.tools:
                    try:
                        # 核心点：执行结果（无论成功失败）都封装为 Observation
                        observation = self.tools[tool_name](**args)
                    except Exception as e:
                        observation = f"Tool Error: {str(e)}"
                else:
                    observation = f"Error: Tool '{tool_name}' not found."

            # 4. 将观察结果反馈给大脑，进入下一轮循环 (自我纠正的关键)
            print(f"👁️ [Observation]: {observation}")
            self.history.append({"role": "tool", "content": observation, "name": tool_name if not action_req.get("error") else "system"})

        if current_step >= self.max_steps:
            print("\n⚠️ [Max Steps Reached] Force stopping to prevent infinite loop.")

        return self.history
