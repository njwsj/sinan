# sinan/agents/coder.py

import hashlib

from sinan.agents.state import GenerationState
from sinan.models.enums import PipelineState
import json
from sinan.agents.llm import LLMClient
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
    8. 不要任何解释文字，直接输出 HTML
    9. 禁止使用 Material Icons、Font Awesome、Bootstrap Icons 等需要外部 CDN 字体的图标库
       （内网无法加载字体，图标会退化成英文文字）；需要图标时统一用 SVG inline 或 Unicode emoji
    10. 图表容器必须设置固定像素高度（如 style="height:400px"），禁止依赖内容撑开
    11. echarts.init() 必须在 DOMContentLoaded 或 window.onload 之后执行，之后立即 chart.resize()
    12. legend 统一放 bottom:0；有 legend 时 grid.bottom ≥ 60，同时有 rotate label 时 ≥ 80
    13. 禁止把两个 bar 系列分别绑到不同 y 轴；量纲不同时第二系列必须用 line；双 y 轴 grid.right ≥ 60
    14. 模板字符串中引用的变量名必须与 const/let/var 声明名大小写完全一致
    15. 必须包含 <meta name="viewport" content="width=device-width, initial-scale=1">
    ## 模板规范
    - 如果有模板代码，页面结构、样式和交互需要参考模板内容。
    - 如果有模板代码，图表颜色优先遵循模板配色，不受下方色板规则约束。
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        session_id = state.get("session_id", "")
        marker = state.get("marker")
        round_num = state.get("fix_round", 0)

        user_content = (
            f"用户需求：\n{state.get('user_input', '')}\n\n"
            f"需求分析：\n{_doc_text(state.get('analysis_output'))}\n\n"
            f"设计方案：\n{_doc_text(state.get('design_doc'))}"
        )
        att_context = _build_att_context(state.get("attachments") or [])
        if att_context:
            user_content += att_context
        # Step 12：Skill / 知识库 / 数据源上下文
        external = state.get("external_knowledge") or state.get("skill_result")
        if external:
            user_content += (
                "\n\n外部资料（知识库 + Skill 输出）。若其中含表格或 rows 数据，"
                "必须直接用于图表 series data，字段名保持一致，禁止编造数值：\n"
                f"{external}"
            )
        ds_context = _build_datasource_context(state.get("datasource_context"))
        if ds_context:
            user_content += ds_context

        # 模板代码注入（对齐参考 coder.py:596-613）
        template_code = state.get("template_code")
        if template_code:
            import re as _re
            # 检测模板使用的图表库，提示 LLM 不要替换
            if _re.search(r'chart\.js|chart\.umd|chart\.min\.js|new\s+Chart\s*\(', template_code, _re.IGNORECASE):
                chart_lib_hint = "（此模板使用 Chart.js，必须保留该图表库，不得替换为其他库）"
            elif _re.search(r'echarts', template_code, _re.IGNORECASE):
                chart_lib_hint = "（此模板使用 ECharts，必须保留该图表库，不得替换为其他库）"
            else:
                chart_lib_hint = ""
            # 压缩模板：去注释、合并空白，减少 token 占用
            minified = _re.sub(r'<!--.*?-->', '', template_code, flags=_re.DOTALL)
            minified = _re.sub(r'>\s+<', '><', minified)
            minified = _re.sub(r'\s{2,}', ' ', minified).strip()
            user_content += (
                f"\n\n模板代码{chart_lib_hint}（必须严格遵循此模板的结构、配色和风格，"
                f"图表使用与模板相同的库和 API）:\n```html\n{minified}\n```"
            )

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

        code = self._strip_markdown("".join(html_chunks))
        return {
            "code": code,
            "code_hash": hashlib.sha256(code.encode("utf-8", "ignore")).hexdigest(),
            # 参考 GenerationOutput 是多文件结构，当前实际只产出单入口文件
            "code_files": [{"path": "index.html", "content": code,
                            "language": "html", "role": "entry"}],
            "status": "verifying",
            "pipeline_state": PipelineState.GENERATION.value,
        }

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

def _doc_text(value: object) -> str:
    """渲染文档型 state 值：优先 _content，否则回落到 JSON。"""
    if not value:
        return ""
    if isinstance(value, dict):
        content = str(value.get("_content") or "").strip()
        if content:
            return content
        fallback = {k: v for k, v in value.items() if k != "_format" and v not in (None, "")}
        return json.dumps(fallback or value, ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)

def _build_datasource_context(datasource_context: dict | None) -> str:
    """把 data_service.resolve_datasources() 的结果渲染成 coder 可读的上下文。"""
    if not datasource_context:
        return ""
    items = datasource_context.get("items") or []
    parts = []
    for item in items:
        if not item.get("ok"):
            parts.append(f"【数据源：{item.get('name')}（{item.get('type')}）不可用："
                         f"{item.get('error')}，请在页面上给出空态提示，不要编造数据】")
            continue
        sample = item.get("sample_data") or {}
        parts.append(
            f"【数据源：{item.get('name')}（{item.get('type')}）】\n"
            f"字段：{', '.join(str(c) for c in (sample.get('columns') or []))}\n"
            f"共 {sample.get('row_count', 0)} 行，数据：\n"
            f"{json.dumps(sample.get('rows') or [], ensure_ascii=False)}"
        )
    return "\n\n" + "\n\n".join(parts) if parts else ""