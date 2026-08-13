# sinan/agents/graph.py
from langgraph.graph import StateGraph, END
from sinan.agents.state import PageGenState
from sinan.agents.analyzer import AnalyzerAgent
from sinan.agents.designer import DesignerAgent
from sinan.agents.coder import CoderAgent
from sinan.agents.verifier import VerifierAgent
from sinan.agents.llm import LLMClient


def build_graph(llm: LLMClient) -> StateGraph:
    analyzer = AnalyzerAgent(llm)
    designer = DesignerAgent(llm)
    coder = CoderAgent(llm)
    verifier = VerifierAgent()

    graph = StateGraph(PageGenState)

    # 注册节点：节点名 → 异步函数（接收 state，返回更新 dict）
    graph.add_node("analyze", analyzer.run)
    graph.add_node("design", designer.run)
    graph.add_node("code", coder.run)
    graph.add_node("verify", verifier.run)

    # 串行边
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "design")
    graph.add_edge("design", "code")
    graph.add_edge("code", "verify")

    # 条件边：验证通过 → END，验证失败 → 直接 END（Phase 3 不做修复，Phase 4 接 Fixer）
    graph.add_conditional_edges(
        "verify",
        lambda state: "end" if state["verified"] else "end",  # Phase 4 改为走 fixer
        {"end": END},
    )

    return graph.compile()