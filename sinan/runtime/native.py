# sinan/runtime/native.py
"""NativeLangGraphRuntime：把现有 LangGraph 图包成 GenerationRuntime 接口。

所有节点事件在这里从 LangGraph 的 astream_events 格式转换为 RuntimeEvent，
Runner 不再感知 astream_events 的内部格式。
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from sinan.runtime.events import RuntimeEvent

logger = logging.getLogger(__name__)

_STEP_LABELS: dict[str, str] = {
    "router": "正在识别需求意图...",
    "skill": "正在准备外部资料...",
    "analyst": "正在分析需求...",
    "designer": "正在制定设计方案...",
    "coder": "AI 正在生成页面代码...",
    "verifier": "正在验证页面...",
    "fixer": "正在修复问题...",
}


class NativeLangGraphRuntime:
    """将 LangGraph astream_events 转换为 RuntimeEvent 流。"""

    def __init__(self, graph) -> None:
        self._graph = graph

    async def run_generation(
        self,
        initial_state: dict[str, Any],
        *,
        thread_id: str,
    ) -> AsyncIterator[RuntimeEvent]:
        async for event in self._stream(initial_state, thread_id=thread_id):
            yield event

    async def resume(self, thread_id: str) -> AsyncIterator[RuntimeEvent]:
        yield RuntimeEvent("runtime_error", {"message": "NativeLangGraphRuntime 不支持 resume"})

    async def iterate(
        self,
        resume_state: dict[str, Any],
        *,
        thread_id: str,
    ) -> AsyncIterator[RuntimeEvent]:
        async for event in self._stream(resume_state, thread_id=thread_id):
            yield event

    async def _stream(
        self,
        state: dict[str, Any],
        *,
        thread_id: str,
    ) -> AsyncIterator[RuntimeEvent]:
        """将 astream_events v2 转换为 RuntimeEvent，暴露节点级步骤事件和最终状态。"""
        final_output: dict[str, Any] | None = None

        async for lg_event in self._graph.astream_events(
            state,
            config={"configurable": {"thread_id": thread_id}},
            version="v2",
        ):
            kind = lg_event["event"]
            name = lg_event.get("name", "")

            if kind == "on_chain_start":
                node_name = lg_event.get("metadata", {}).get("langgraph_node", "")
                if node_name in _STEP_LABELS:
                    yield RuntimeEvent("step", {
                        "step": node_name,
                        "message": _STEP_LABELS[node_name],
                        "agent": node_name,
                    })

            elif kind == "on_chain_end":
                if lg_event.get("run_id") and name == "LangGraph":
                    final_output = lg_event["data"].get("output")

        if final_output is not None:
            yield RuntimeEvent("graph_output", final_output)
