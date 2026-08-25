# sinan/runtime/registry.py
"""RuntimeRegistry：按 mode 字段选择对应 Runtime。

当前支持：
  native      → NativeLangGraphRuntime
  claude_code → ClaudeCodeRuntime（Step 13，底层也是 native）
  opencode    → Step 14 实现

mode 来自 GenerateRequest.mode，默认 "native"。
"""
from __future__ import annotations

import logging

from sinan.runtime.native import NativeLangGraphRuntime

logger = logging.getLogger(__name__)

_MODE_ALIASES: dict = {
    "": "native",
    None: "native",
    "default": "native",
}


class RuntimeRegistry:
    """持有各 Runtime 实例，按 mode 路由。"""

    def __init__(self, graph) -> None:
        self._graph = graph
        self._native = NativeLangGraphRuntime(graph)

    def get(self, mode: str | None):
        """返回对应 mode 的 Runtime 实例。未知 mode 降级到 native 并记录警告。"""
        resolved = _MODE_ALIASES.get(mode, mode) if mode in _MODE_ALIASES else (mode or "native")

        if resolved == "native":
            return self._native

        if resolved == "claude_code":
            from sinan.claude_code.runtime import ClaudeCodeRuntime
            return ClaudeCodeRuntime(self._graph)

        logger.warning("unknown runtime mode %r, falling back to native", mode)
        return self._native
