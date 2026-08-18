# sinan/agents/designer.py
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState
from sinan.services.generation_event_bus import event_bus
from sinan.models import events

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
        session_id = state.get("session_id", "")
        marker = state.get("marker")
        user_content = f"用户需求：\n{state['prompt']}\n\n需求分析：\n{state['requirements']}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # 流式生成，逐 token 推 design_delta 事件
        chunks: list[str] = []
        accumulated_len = 0
        async for token in self.llm.astream(messages, temperature=0.5):
            chunks.append(token)
            accumulated_len += len(token)
            if session_id:
                await event_bus.publish(
                    session_id, events.DESIGN_DELTA,
                    events.design_delta_data(token, accumulated_len),
                    marker=marker,
                )
        design = "".join(chunks)
        # 流结束后推一条完整内容事件，方便断线重连后直接填充
        if session_id:
            await event_bus.publish(
                session_id, events.DESIGN_RESULT,
                events.design_result_data(design),
                marker=marker,
            )
        return {"design": design}