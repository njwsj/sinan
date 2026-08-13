# sinan/agents/designer.py
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState

SYSTEM_PROMPT = """你是一个前端 UI 设计师。
根据需求分析结果，输出具体的页面设计方案。

输出格式（纯文本，不要 markdown）：
1. 整体布局描述（如：顶部导航 + 左侧面板 + 右侧主区域）
2. 配色方案（主色、辅色、背景色的具体十六进制值）
3. 组件清单（每个组件一行，说明用途和位置）
4. 数据展示方式（表格/图表/卡片，及图表类型）

直接输出设计方案，不要任何前缀说明。"""


class DesignerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        user_content = f"用户需求：\n{state['prompt']}\n\n需求分析：\n{state['requirements']}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        design = await self.llm.chat(messages, temperature=0.5)
        return {"design": design}