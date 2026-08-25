# sinan/runtime/events.py
"""Runtime 事件原语，对齐 page/claude_code/events.py。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeEvent:
    """Runtime 层产生的归一化事件。由各 Runtime 实现发出，由 Runner 转换为 SSEEvent。"""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
