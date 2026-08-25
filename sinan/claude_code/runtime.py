# sinan/claude_code/runtime.py
"""ClaudeCodeRuntime：对齐 page/claude_code/runtime.py。

当前 sinan 的 Claude Code 后端是 native（即 NativeLangGraphRuntime），
与参考项目 backend="native" 语义一致。
"""
from __future__ import annotations

from typing import Any, AsyncIterator

from sinan.config.settings import settings
from sinan.runtime.events import RuntimeEvent
from sinan.runtime.native import NativeLangGraphRuntime


class ClaudeCodeRuntime:
    """通过 native 后端运行页面生成，对齐 page/claude_code/runtime.py。"""

    def __init__(self, graph, *, backend: str | None = None) -> None:
        backend = backend or getattr(settings, "claude_code_backend", "native")
        if backend != "native":
            raise ValueError(f"Unsupported claude_code backend: {backend}")
        self._inner = NativeLangGraphRuntime(graph)

    async def run_generation(
        self,
        initial_state: dict[str, Any],
        *,
        thread_id: str,
    ) -> AsyncIterator[RuntimeEvent]:
        async for event in self._inner.run_generation(initial_state, thread_id=thread_id):
            yield event

    async def resume(self, thread_id: str) -> AsyncIterator[RuntimeEvent]:
        yield RuntimeEvent("step", {"step": "resuming", "message": "恢复会话", "agent": "runtime"})
        async for event in self._inner.resume(thread_id):
            yield event

    async def iterate(
        self,
        resume_state: dict[str, Any],
        *,
        thread_id: str,
    ) -> AsyncIterator[RuntimeEvent]:
        async for event in self._inner.iterate(resume_state, thread_id=thread_id):
            yield event
