# sinan/runtime/base.py
"""GenerationRuntime Protocol——所有 Runtime 实现的公共接口。"""
from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable

from sinan.runtime.events import RuntimeEvent


@runtime_checkable
class GenerationRuntime(Protocol):
    """各 Runtime（NativeLangGraph / ClaudeCode / Opencode）的统一接口。

    Runner 只与这个 Protocol 交互，不了解各 Runtime 内部实现。
    """

    async def run_generation(
        self,
        initial_state: dict[str, Any],
        *,
        thread_id: str,
    ) -> AsyncIterator[RuntimeEvent]:
        ...

    async def resume(self, thread_id: str) -> AsyncIterator[RuntimeEvent]:
        ...

    async def iterate(
        self,
        resume_state: dict[str, Any],
        *,
        thread_id: str,
    ) -> AsyncIterator[RuntimeEvent]:
        ...
