# sinan/agents/designer.py
"""Designer Agent：产出 markdown 设计文档 + DESIGN_JSON 结构化设计。

对齐参考 page/agents/designer.py。design_doc 的结构化部分（layout /
component_tree / style_tokens）被 coder 和 RequirementValidator 使用，
所以 DESIGN_JSON 解析失败时必须给出可用的兜底结构而不是空 dict。
"""
from __future__ import annotations

import json
import re

from sinan.agents.llm import LLMClient
from sinan.agents.state import GenerationState
from sinan.models import events
from sinan.models.enums import PipelineState
from sinan.services.generation_event_bus import event_bus

SYSTEM_PROMPT = """你是资深数据可视化设计师。根据需求分析文档，设计完整的页面布局方案。

请用Markdown格式输出详细的设计文档，每个部分都有具体说明。

# 设计方案

## 一、整体布局
- **布局方式**: grid/flex
- **栅格系统**: 12列
- **整体结构描述**:

### 区域划分

| 区域 | 位置 | 栅格占比 | 高度 | 说明 |
|------|------|----------|------|------|

## 二、组件设计
### 2.1 [组件名称]
- **类型**: number_card / bar_chart / line_chart / pie_chart / table / filter / title
- **标题**:
- **数据字段**:
- **展示逻辑**:
- **位置**:

## 三、交互设计

| 触发条件 | 动作 | 影响范围 | 说明 |
|----------|------|----------|------|

## 四、数据绑定

| 组件 | 绑定字段 | 转换逻辑 |
|------|----------|----------|

## 五、样式规范
- **主色**: #HEX
- **背景色**: #HEX
- **卡片圆角**: 8px
- **阴影**:
- **字体层级**:

---
<!-- DESIGN_JSON
{
  "layout": {"type": "grid", "columns": 12, "sections": [{"name": "区域名", "span": 列数, "height": "高度"}]},
  "component_tree": {
    "component_id": "root",
    "component_type": "page",
    "props": {},
    "children": [
      {"component_id": "唯一ID", "component_type": "类型", "props": {"title":"标题","field":"字段"}, "children": []}
    ]
  },
  "style_tokens": {"primary": "#主色", "bg": "#背景色", "card_radius": "8px"}
}
DESIGN_JSON -->

要求：
- 每个组件都要写清楚数据字段和展示逻辑
- component_type 可选: number_card, bar_chart, line_chart, pie_chart, table, filter, title
- 核心指标放最显眼位置；图表类型匹配数据特征
- 最后的 DESIGN_JSON 块必须存在且为合法 JSON"""

_DEFAULT_DESIGN_JSON = {
    "layout": {"type": "grid", "columns": 12, "sections": [{"name": "main", "span": 12}]},
    "component_tree": {"component_id": "root", "component_type": "page", "props": {}, "children": []},
    "style_tokens": {"primary": "#4E6EF2", "bg": "#F7F7F9"},
}


def _extract_design_json(md_text: str) -> dict:
    """提取 DESIGN_JSON 块，失败时返回兜底结构（不能返回空 dict）。"""
    match = re.search(r"<!--\s*DESIGN_JSON\s*(.*?)\s*DESIGN_JSON\s*-->", md_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    return json.loads(json.dumps(_DEFAULT_DESIGN_JSON))


def _strip_design_json(md_text: str) -> str:
    clean = re.sub(r"\s*<!--\s*DESIGN_JSON\s*.*?DESIGN_JSON\s*-->", "", md_text, flags=re.DOTALL)
    return re.sub(r"\s*---\s*\n?DESIGN_JSON\s*-->", "", clean, flags=re.DOTALL).strip()


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


def build_designer_context(state: GenerationState) -> str:
    analysis = state.get("analysis_output")
    if not analysis:
        return f"用户修改意见: {state.get('iteration_feedback') or state.get('user_input', '')}"
    context = f"以下是确认后的需求分析文档:\n\n{_doc_text(analysis)}"
    template_code = state.get("template_code")
    if template_code:
        # 模板注入属于 Step 11，这里先按参考的压缩方式预留
        minified = re.sub(r"<script[^>]*>.*?</script>", "", template_code, flags=re.DOTALL | re.IGNORECASE)
        minified = re.sub(r"<!--.*?-->", "", minified, flags=re.DOTALL)
        minified = re.sub(r">\s+<", "><", minified)
        minified = re.sub(r"\s{2,}", " ", minified).strip()
        context += (
            "\n\n参考模板（必须保留其整体风格、配色、布局结构，在此基础上填充内容）:\n"
            f"```html\n{minified}\n```"
        )
    return context


def parse_designer_response(md_content: str) -> dict:
    design_json = _extract_design_json(md_content)
    return {
        "design_doc": {
            "_format": "markdown",
            "_content": _strip_design_json(md_content),
            **design_json,
        },
        "status": "coding",
        "pipeline_state": PipelineState.DESIGN.value,
    }


class DesignerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        session_id = state.get("session_id", "")
        marker = state.get("marker")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_designer_context(state)},
        ]

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
        md_content = "".join(chunks)
        if session_id:
            await event_bus.publish(
                session_id, events.DESIGN_RESULT,
                events.design_result_data(_strip_design_json(md_content)),
                marker=marker,
            )
        return parse_designer_response(md_content)