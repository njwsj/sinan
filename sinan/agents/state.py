# sinan/agents/state.py
from typing import TypedDict


class PageGenState(TypedDict):
    """LangGraph 节点之间共享的流水线状态。"""

    # 输入
    prompt: str

    # Analyzer 产出
    requirements: str       # 结构化需求：功能列表、交互要点

    # Designer 产出
    design: str             # 设计方案：布局结构、配色方案、组件清单

    # Coder 产出
    html: str               # 生成的 HTML 页面

    # Verifier 产出
    verified: bool          # 是否通过验证
    verify_message: str     # 验证结论或错误描述

    # Phase 4 新增：Harness 控制字段
    iteration: int  # 当前修复迭代次数（从 0 开始）
    max_iterations: int  # 最大允许修复次数（默认 3）
    gate_decision: str  # 当前门禁决策（proceed/retry/fix/block）
