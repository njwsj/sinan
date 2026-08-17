# sinan/agents/coder.py
import json
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState
from sinan.services.generation_event_bus import event_bus
from sinan.models import events


def _build_att_context(attachments: list) -> str:
    """
    从 state["attachments"] 构造代码生成用的数据上下文。
    Coder 需要完整的 rows 才能把真实数据写进 ECharts series data。
    对齐原项目：全量 rows，不截断。
    """
    if not attachments:
        return ""
    parts = []
    for att in attachments:
        parsed = att.get("parsed") or {}
        cols = parsed.get("columns") or att.get("columns") or []
        rows = parsed.get("rows") or []
        row_count = parsed.get("row_count") or len(rows)
        filename = att.get("filename", "未知文件")

        parts.append(
            f"【数据源：{filename}】\n"
            f"字段：{', '.join(str(c) for c in cols)}\n"
            f"共 {row_count} 行，完整数据（直接用于 ECharts series data）：\n"
            f"{json.dumps(rows, ensure_ascii=False)}"
        )
    return "\n\n" + "\n\n".join(parts) + "\n\n请在图表中使用以上真实数据，字段名保持与数据源一致。"


class CoderAgent:

    SYSTEM_PROMPT = """你是一个前端页面生成专家。
    根据需求分析和设计方案，生成一个完整的、可直接在浏览器运行的 HTML 页面。

    要求：
    1. 页面必须是完整的 HTML 文档，包含 <!DOCTYPE html>、<head>、<body>
    2. CSS 全部内联在 <style> 标签中，不依赖外部 CSS 文件
    3. JavaScript 全部内联在 <script> 标签中
    4. 如果需要图表，使用 ECharts（通过 CDN 引入：https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js）
    5. 响应式布局，适配不同屏幕宽度
    6. 现代化 UI 风格，配色协调，有适当的间距和层次感
    7. 只返回纯 HTML 代码，不要任何 markdown 格式（不要 ```html 包裹）
    8. 不要任何解释文字，直接输出 HTML"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        session_id = state.get("session_id", "")
        marker = state.get("marker")
        round_num = state.get("iteration", 0)
        user_content = (
            f"用户需求：\n{state['prompt']}\n\n"
            f"需求分析：\n{state['requirements']}\n\n"
            f"设计方案：\n{state['design']}"
        )

        # 从结构化 attachments 读取完整数据，注入 prompt
        att_context = _build_att_context(state.get("attachments", []))
        if att_context:
            user_content += att_context

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        html_chunks: list[str] = []
        accumulated_len = 0

        if session_id:
            await event_bus.publish(
                session_id, events.CODE_START,
                events.code_start_data(round_num=round_num), marker=marker,
            )
        async for token in self.llm.astream(messages, temperature=0.3):
            html_chunks.append(token)
            accumulated_len += len(token)
            if session_id:
                await event_bus.publish(
                    session_id, events.CODE_DELTA,
                    events.code_delta_data(token, accumulated_len), marker=marker,
                )
        if session_id:
            await event_bus.publish(
                session_id, events.CODE_STREAM_END,
                events.code_stream_end_data(accumulated_len, round_num=round_num),
                marker=marker,
            )
        html = self._strip_markdown("".join(html_chunks))
        return {"html": html}

    def _strip_markdown(self, text: str) -> str:
        """
        剥离 LLM 有时会加上的 markdown 代码块包裹。
        处理以下几种常见格式：
          ```html\n...\n```
          ```\n...\n```
        """
        text = text.strip()
        # 处理 ```html 开头
        if text.startswith("```html"):
            text = text[7:]
        # 处理 ``` 开头（没有语言标识）
        elif text.startswith("```"):
            text = text[3:]
        # 处理 ``` 结尾
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()
