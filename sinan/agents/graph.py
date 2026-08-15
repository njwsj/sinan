# sinan/agents/graph.py
import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from sinan.agents.state import PageGenState
from sinan.agents.analyzer import AnalyzerAgent
from sinan.agents.designer import DesignerAgent
from sinan.agents.coder import CoderAgent
from sinan.agents.verifier import VerifierAgent
from sinan.agents.fixer import FixerAgent
from sinan.agents.llm import LLMClient
from sinan.harness.gates import GateEngine

logger = logging.getLogger(__name__)

def build_graph(llm: LLMClient) -> StateGraph:
    analyzer = AnalyzerAgent(llm)
    designer = DesignerAgent(llm)
    coder = CoderAgent(llm)
    verifier = VerifierAgent()
    fixer = FixerAgent(llm)
    gate_engine = GateEngine()

    # 门禁节点（不调用 LLM，只做决策）
    async def gate_analyze(state: PageGenState) -> dict:
        result = gate_engine.evaluate("analyze", state)
        logger.info("gate_analyze: decision=%s", result.decision)
        return {"gate_decision": result.decision}

    async def gate_design(state: PageGenState) -> dict:
        result = gate_engine.evaluate("design", state)
        logger.info("gate_design: decision=%s", result.decision)
        return {"gate_decision": result.decision}

    async def gate_code(state: PageGenState) -> dict:
        result = gate_engine.evaluate("code", state)
        logger.info("gate_code: decision=%s, issues=%s", result.decision, result.issues)
        return {"gate_decision": result.decision}

    async def gate_verify(state: PageGenState) -> dict:
        result = gate_engine.evaluate("verify", state)
        logger.info("gate_verify: decision=%s", result.decision)
        return {"gate_decision": result.decision}

    graph = StateGraph(PageGenState)

    # 注册节点：节点名 → 异步函数（接收 state，返回更新 dict）
    graph.add_node("analyze", analyzer.run)
    graph.add_node("gate_analyze", gate_analyze)
    graph.add_node("design", designer.run)
    graph.add_node("gate_design", gate_design)
    graph.add_node("code", coder.run)
    graph.add_node("gate_code", gate_code)
    graph.add_node("verify", verifier.run)
    graph.add_node("gate_verify", gate_verify)
    graph.add_node("fix", fixer.run)

    # 连边：业务节点 → 门禁节点
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "gate_analyze")
    graph.add_conditional_edges(
        "gate_analyze",
        lambda s: s.get("gate_decision", "proceed"),
        {"proceed": "design", "retry": "analyze"},
    )
    graph.add_edge("design", "gate_design")
    graph.add_conditional_edges(
        "gate_design",
        lambda s: s.get("gate_decision", "proceed"),
        {"proceed": "code", "retry": "design"},
    )
    graph.add_edge("code", "gate_code")
    # code 的门禁有 3 种决策：proceed, fix, block,当没问题时走 verify，有问题且没用超过最大修复次数时走 fix ，当超过最大修复次数时直接 block
    graph.add_conditional_edges(
        "gate_code",
        lambda s: s.get("gate_decision", "proceed"),
        {"proceed": "verify", "fix": "fix", "block": END},
    )
    graph.add_edge("verify", "gate_verify")
    graph.add_conditional_edges(
        "gate_verify",
        lambda s: s.get("gate_decision", "proceed"),
        {"proceed": END, "retry": "fix", "block": END},
    )

    # fix 之后重新走 code（修复后重新验证）
    graph.add_edge("fix", "code")

    # Checkpoint：开发阶段用内存版，生产换 AsyncMySqlSaver 时只改这一行
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)