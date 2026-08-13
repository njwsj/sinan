# sinan/agents/analyzer.py
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState

SYSTEM_PROMPT = """你是一个需求分析专家。
分析用户的页面需求，输出结构化的需求清单。

输出格式（纯文本，不要 markdown）：
1. 核心功能列表（每条一行）
2. 数据展示要求
3. 交互要点
4. 特殊约束（如：必须用 ECharts、响应式等）

直接输出分析结果，不要任何前缀说明。"""


class AnalyzerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": state["prompt"]},
        ]
        requirements = await self.llm.chat(messages, temperature=0.3)
        return {"requirements": requirements}