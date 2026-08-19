# sinan/agents/fixer.py
"""Fixer Agent：按验证问题修复代码。

对齐参考 page/agents/fixer.py：
- 修复策略按轮次递增：1=conservative，2=moderate，3+=aggressive；
- prompt 里带完整上下文（原始需求、需求分析、设计、原始数据、模板）+ 结构化 issues（最多 10 条）；
- 每轮往 fix_history 追加一条记录；
- 修复后 pipeline_state 回到 generation（对齐参考 VALIDATION → GENERATION 的 repair_needed 转移）。
"""
from __future__ import annotations

import hashlib
import json
import logging

from sinan.agents.llm import LLMClient
from sinan.agents.state import GenerationState
from sinan.models import events
from sinan.models.enums import PipelineState, RepairStrategy
from sinan.services.generation_event_bus import event_bus

logger = logging.getLogger(__name__)

STRATEGY_BY_ROUND = {
    1: RepairStrategy.CONSERVATIVE,
    2: RepairStrategy.MODERATE,
    3: RepairStrategy.AGGRESSIVE,
}

SYSTEM_PROMPT_TEMPLATE = """你是一个前端代码修复工程师。根据验证报告修复页面代码中的问题。

修复策略: {strategy}
- conservative: 仅修改导致问题的最小代码范围
- moderate: 允许局部重构相关组件
- aggressive: 允许替换实现方案

修复后必须同时满足以下验证规则：

需求一致性（P0/P1 阻断问题）：
- 页面必须包含 <body> 标签，代码不能为空
- 需求分析中要求的核心组件（图表、表格、筛选、指标卡等）必须实现
- 验收标准中的关键要求（如响应式 viewport）必须满足

数据一致性：
- 数据字段名必须与用户上传文件的列名保持一致
- 指标数值应从数据中计算得出，不应硬编码到 innerHTML/textContent

图标规范：
- 禁止使用 Material Icons、Font Awesome 等需要外部 CDN 字体的图标库
- 需要图标时统一使用 SVG inline 或 Unicode emoji

ECharts 规范：
- 图表容器必须设置固定像素高度，禁止依赖内容撑开
- echarts.init() 必须在 DOMContentLoaded 之后执行，之后立即 chart.resize()
- legend 放 bottom:0；有 legend 时 grid.bottom ≥ 60，同时有 rotate label 时 ≥ 80
- 禁止两个 bar 系列分别绑不同 y 轴；双 y 轴 grid.right ≥ 60

JS 代码规范：
- 模板字符串中引用的变量名必须与声明名大小写完全一致
- 对空值/null/undefined 做兜底，避免 NaN 或脚本错误

编码约束：
- 只修复问题，不引入无关功能

本轮修复上下文：
{context}

验证未通过问题（只基于这些问题修复）：
{issues}

当前代码:
{code}

只返回修复后的完整HTML代码，不要包含```标记或其他说明文字。"""


def _doc_text(value: object) -> str:
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


def _raw_data_context(state: GenerationState) -> str:
    parts = []
    for att in state.get("attachments") or []:
        parsed = att.get("parsed") or {}
        cols = att.get("columns") or parsed.get("columns") or []
        rows = parsed.get("rows") or []
        if cols or rows:
            part = f"文件: {att.get('filename', '')}"
            if cols:
                part += f"\n列名: {', '.join(str(c) for c in cols)}"
            if rows:
                part += f"\n完整数据: {json.dumps(rows, ensure_ascii=False)}"
            parts.append(part)
    return "\n\n".join(parts)


def _section(title: str, value: object) -> str:
    text = _doc_text(value)
    return f"\n\n## {title}\n{text}" if text else ""


def _repair_context(state: GenerationState) -> str:
    parts = [
        _section("用户原始需求", state.get("user_input")),
        _section("本轮迭代/修复反馈", state.get("iteration_feedback")),
        _section("需求分析", state.get("analysis_output")),
        _section("页面设计", state.get("design_doc")),
        _section("原始数据区", _raw_data_context(state)),
        _section("外部知识/工具结果", state.get("external_knowledge")),
    ]
    return "".join(p for p in parts if p).strip() or "无额外上下文"


class FixerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        session_id = state.get("session_id", "")
        marker = state.get("marker")
        fix_round = state.get("fix_round", 0) + 1
        strategy = STRATEGY_BY_ROUND.get(fix_round, RepairStrategy.AGGRESSIVE)
        issues = (state.get("verification_result") or {}).get("issues", [])

        logger.info("fixer: round=%d strategy=%s issues=%d", fix_round, strategy.value, len(issues))
        if session_id:
            await event_bus.publish(
                session_id, events.FIX_START,
                events.fix_start_data(fix_round, strategy.value, len(issues)),
                marker=marker,
            )

        prompt = SYSTEM_PROMPT_TEMPLATE.format(
            strategy=strategy.value,
            context=_repair_context(state),
            issues=json.dumps(issues[:10], ensure_ascii=False),
            code=state.get("code") or "",
        )
        response = await self.llm.chat([{"role": "user", "content": prompt}], temperature=0.2)
        code = self._strip_markdown(response)

        fix_history = list(state.get("fix_history") or [])
        fix_history.append({
            "round": fix_round,
            "strategy": strategy.value,
            "issues_before": len(issues),
        })

        if session_id:
            await event_bus.publish(
                session_id, events.FIX_APPLIED,
                events.fix_applied_data(fix_round, strategy.value, len(issues)),
                marker=marker,
            )

        return {
            "code": code,
            "code_hash": hashlib.sha256(code.encode("utf-8", "ignore")).hexdigest(),
            "code_files": [
                {"path": "index.html", "content": code, "language": "html", "role": "entry"}
            ],
            "fix_round": fix_round,
            "fix_history": fix_history,
            "repair_strategy": strategy.value,
            "status": "verifying",
            "pipeline_state": PipelineState.GENERATION.value,
        }

    def _strip_markdown(self, text: str) -> str:
        text = (text or "").strip()
        if text.startswith("```html"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()