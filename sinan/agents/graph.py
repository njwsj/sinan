# sinan/agents/graph.py
"""LangGraph 图编排：6 节点 + 2 条件边。

对齐参考 page/agents/graph.py：

    router → skill → analyst → (条件) → designer → coder → verifier → (条件)
               │                └→ END(awaiting_confirmation)         ├→ fixer → verifier
               └→ END(skill_link_required)                           └→ END

与 Step 6 之前的差异：删除 gate_analyze / gate_design / gate_code / gate_verify
四个独立门禁节点。门禁不再决定路由，而是由 harness.orchestrator.wrap_node
在节点执行后统一评估并写报告；路由只由 verification_result 与 fix_round 决定。
这与参考一致，也让 gate 报告能覆盖 router/analyst/designer 这些原来没有门的步骤。
"""
from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from sinan.agents.analyzer import AnalyzerAgent
from sinan.agents.coder import CoderAgent
from sinan.agents.designer import DesignerAgent
from sinan.agents.fixer import FixerAgent
from sinan.agents.llm import LLMClient
from sinan.agents.router import RouterAgent
from sinan.agents.state import GenerationState
from sinan.agents.verifier import VerifierAgent
from sinan.config.settings import settings
from sinan.harness.orchestrator import wrap_node
from sinan.agents.skill_agent import SkillAgent

logger = logging.getLogger(__name__)


def _after_analyst(state: GenerationState) -> str:
    """analyst 之后：低置信度挂起等确认则终止，否则继续设计。"""
    if state.get("user_confirmed") is None and state.get("status") == "awaiting_confirmation":
        return "end"
    return "designer"

def _after_skill(state: GenerationState) -> str:
    """skill 之后：缺必要链接则挂起终止，否则进入需求分析。"""
    if state.get("skill_link_required"):
        return "end"
    return "analyst"


def _should_fix(state: GenerationState) -> str:
    """verifier 之后：通过则完成；未通过且未超轮次则修复；超轮次带警告完成。"""
    result = state.get("verification_result") or {}
    fix_round = state.get("fix_round", 0)
    max_rounds = state.get("max_fix_rounds", settings.max_fix_rounds)
    if result.get("passed", False):
        return "complete"
    if fix_round >= max_rounds:
        return "complete_with_warnings"
    return "fix"


def build_graph(llm: LLMClient):
    """构建并编译流水线图。"""
    router = RouterAgent(llm)
    skill = SkillAgent(llm)
    analyst = AnalyzerAgent(llm)
    designer = DesignerAgent(llm)
    coder = CoderAgent(llm)
    verifier = VerifierAgent()
    fixer = FixerAgent(llm)

    builder = StateGraph(GenerationState)
    builder.add_node("router", wrap_node(router.run, "router"))
    # skill 不套 harness：无对应契约与门禁，与 fixer 处理方式一致
    builder.add_node("skill", skill.run)
    builder.add_node("analyst", wrap_node(analyst.run, "analyst"))
    builder.add_node("designer", wrap_node(designer.run, "designer"))
    builder.add_node("coder", wrap_node(coder.run, "coder"))
    builder.add_node("verifier", wrap_node(verifier.run, "verifier"))
    # fixer 不套 harness：它属于修复路径，产物由紧随其后的 verifier 统一评估
    builder.add_node("fixer", fixer.run)

    builder.set_entry_point("router")
    builder.add_edge("router", "skill")  # 原为 router → analyst
    builder.add_conditional_edges("skill", _after_skill,
                                  {"analyst": "analyst", "end": END})  # 新增
    builder.add_conditional_edges("analyst", _after_analyst,
                                  {"designer": "designer", "end": END})
    builder.add_edge("designer", "coder")
    builder.add_edge("coder", "verifier")
    builder.add_conditional_edges("verifier", _should_fix,
                                  {"fix": "fixer", "complete": END,
                                   "complete_with_warnings": END})
    builder.add_edge("fixer", "verifier")

    # Checkpoint：开发阶段用内存版，生产换 AsyncMySqlSaver 时只改这一行
    return builder.compile(checkpointer=MemorySaver())