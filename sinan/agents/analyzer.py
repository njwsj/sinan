# sinan/agents/analyzer.py
"""Analyst Agent：产出完整的 markdown 需求分析文档。

对齐参考 page/agents/analyst.py：
- 输出 markdown 正文 + 尾部 META_JSON 块（confidence_score / confirmation_digest）；
- confidence < settings.auto_confirm_threshold 且非迭代场景时，
  返回 status="awaiting_confirmation" + user_confirmed=None，让图在 analyst 后终止；
- 否则 user_confirmed=True，继续走 designer。

sinan 差异（保留 Step 5 行为）：analyst 用流式调用并逐 token 推 analysis_delta 事件，
参考用非流式 ainvoke。事件协议是 sinan 已固化的，不回退。
"""
from __future__ import annotations

import json
import re

from sinan.agents.llm import LLMClient
from sinan.agents.state import GenerationState
from sinan.config.settings import settings
from sinan.models import events
from sinan.models.enums import PipelineState
from sinan.services.generation_event_bus import event_bus

SYSTEM_PROMPT = """你是一个资深产品经理和需求分析师。根据用户需求和数据信息，生成完整、详细的需求分析文档。

**重要：判断需求是否清晰**
- 默认不要打断用户确认；大多数页面、看板、HTML、图表生成需求都应直接进入生成流程
- 只有完全无法判断页面主题、核心目标或用户意图时，才将 confidence_score 设为 0.3 以下
- 此时在文档开头添加"## 澄清问题"章节，列出必须确认的关键问题（1-3个）
- 如果只是缺少细节（如配色、筛选项、数据为空展示），请自行采用合理默认值，不要要求用户确认

**重要：数据列关系处理原则（必须严格遵守）**
- 禁止自行推测数据列之间的计算/汇总关系（如不得自行定义"总收入 = 内部收入 + 跨BG收入"）
- 只有用户明确说明该关系，或用数据中实际数值逐行校验通过，才可以使用跨列计算关系
- 否则只展示原始列数据，不做跨列聚合计算
- 字段名含义不明确或疑似口径歧义时，在"澄清问题"章节中列出

判断标准：
- "做一个页面" → 不清晰 confidence < 0.3
- "做一个时间的页面" → 可直接生成 confidence >= 0.75
- "做一个销售数据看板，包含营收趋势图和客户分布" → 清晰 confidence >= 0.85

请用Markdown格式输出完整的需求文档，每个章节不少于2-3句话。格式如下：

# 需求分析文档

## 澄清问题（仅当需求不清晰时输出此章节）

## 一、应用概述
- **名称**:
- **描述**:

## 二、用户与使用场景
- **目标用户**:
- **核心场景**:
- **使用频率**:

## 三、数据方案
- **数据来源**:
- **处理逻辑**:

**数据字段清单:**

| 字段名 | 含义 | 类型 | 用途说明 |
|--------|------|------|----------|

## 四、页面结构与功能
### 4.1 [区域名称]
- **功能**:
- **组件**:
- **数据映射**:
- **布局**:

## 五、业务规则
### 交互逻辑
### 展示逻辑

## 六、验收标准
（至少5条具体可验证的标准）

---
<!-- META_JSON
{"confidence_score": 0.0-1.0, "confirmation_digest": "一句话摘要", "page_sections_count": 数字, "fields_count": 数字}
META_JSON -->

要求：
- 每个章节内容要详实具体，不要用占位符
- page_structure 至少 2 个区域
- 如用户提供了数据文件，字段必须基于实际列名
- 最后的 META_JSON 块必须存在且为合法 JSON"""


def _extract_meta_json(md_text: str) -> dict:
    """从 markdown 尾部提取 META_JSON 块，缺失时给默认置信度 0.7。"""
    match = re.search(r"<!--\s*META_JSON\s*(.*?)\s*META_JSON\s*-->", md_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    return {"confidence_score": 0.7, "confirmation_digest": ""}


def _strip_meta_json(md_text: str) -> str:
    """去掉 META_JSON 块，兼容 LLM 少写结尾标签的几种变体。"""
    clean = re.sub(r"\s*<!--\s*META_JSON\s*.*?(?:META_JSON\s*)?-->", "", md_text, flags=re.DOTALL)
    clean = re.sub(r"\s*---\s*\n?META_JSON\s*-->", "", clean, flags=re.DOTALL)
    clean = re.sub(r"\n+META_JSON\s*$", "", clean, flags=re.MULTILINE)
    return clean.strip()


def _build_att_context(attachments: list) -> str:
    """需求分析用的数据上下文：字段名（前20）+ 行数 + 完整 rows。"""
    if not attachments:
        return ""
    parts = []
    for att in attachments:
        parsed = att.get("parsed") or {}
        cols = att.get("columns") or parsed.get("columns") or []
        rows = parsed.get("rows") or []
        row_count = att.get("row_count") or parsed.get("row_count") or len(rows)
        info = f"- {att.get('filename', '未知文件')}: {', '.join(str(c) for c in cols[:20])}"
        if row_count:
            info += f" ({row_count}行)"
        if rows:
            info += f"\n  完整数据: {json.dumps(rows, ensure_ascii=False)}"
        parts.append(info)
    return "\n\n用户上传的数据文件(请基于此数据进行需求分析):\n" + "\n".join(parts)


def build_analyst_context(state: GenerationState) -> str:
    """拼装 analyst 的 user 侧上下文。"""
    context = state.get("user_input", "")
    if state.get("intent"):
        context += f"\n\n路由分析结果: {json.dumps(state['intent'], ensure_ascii=False)}"
    if state.get("code") and state.get("iteration_feedback"):
        context += (
            "\n\n当前已生成页面代码（请结合本次修改要求判断是否需要调整需求分析）:\n"
            f"```html\n{state['code']}\n```"
        )
    context += _build_att_context(state.get("attachments") or [])
    return context


def parse_analyst_response(state: GenerationState, md_content: str) -> dict:
    """把 analyst 的 markdown 输出解析成 state 更新。"""
    meta = _extract_meta_json(md_content)
    clean_content = _strip_meta_json(md_content)
    confidence = float(meta.get("confidence_score", 0.7))

    analysis_output = {
        "_format": "markdown",
        "_content": clean_content,
        "confidence_score": confidence,
        "confirmation_digest": meta.get("confirmation_digest", md_content[:200]),
    }

    # 低置信度且非迭代场景：挂起等用户确认（图在 analyst 之后终止）
    if confidence < settings.auto_confirm_threshold and not state.get("iteration_feedback"):
        return {
            "analysis_output": analysis_output,
            "requirement_doc": md_content,
            "status": "awaiting_confirmation",
            "pipeline_state": PipelineState.USER_CONFIRM.value,
            "user_confirmed": None,
        }
    return {
        "analysis_output": analysis_output,
        "requirement_doc": meta.get("confirmation_digest", ""),
        "status": "designing",
        "pipeline_state": PipelineState.ANALYSIS.value,
        "user_confirmed": True,
    }


class AnalyzerAgent:
    """需求分析。流式输出，逐 token 推 analysis_delta 事件。"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        session_id = state.get("session_id", "")
        marker = state.get("marker")
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_analyst_context(state)},
        ]

        chunks: list[str] = []
        accumulated_len = 0
        async for token in self.llm.astream(messages, temperature=0.3):
            chunks.append(token)
            accumulated_len += len(token)
            if session_id:
                await event_bus.publish(
                    session_id, events.ANALYSIS_DELTA,
                    events.analysis_delta_data(token, accumulated_len),
                    marker=marker,
                )
        md_content = "".join(chunks)
        if session_id:
            await event_bus.publish(
                session_id, events.ANALYSIS_RESULT,
                events.analysis_result_data(_strip_meta_json(md_content)),
                marker=marker,
            )
        return parse_analyst_response(state, md_content)