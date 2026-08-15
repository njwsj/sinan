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
    """
    gate_decision生命周期：
    analyze → gate_analyze 写入 {"gate_decision": "proceed"}
         → design 执行（gate_decision 还是 "proceed"，没人改它）
         → gate_design 写入 {"gate_decision": "proceed"}  ← 覆盖上一次的值
         → code 执行（gate_decision 还是 "proceed"）
         → gate_code 写入 {"gate_decision": "fix"}        ← 覆盖
         → fix 执行（gate_decision 还是 "fix"，没人改它）
    因为条件边只在紧跟着的 gate_xxx 节点执行后立刻读取 gate_decision，读到的就是刚刚写入的最新值。
    业务节点（analyze / design / code 等）本身不读 gate_decision，所以它里面残留什么值都无所谓。
    
    唯一要注意的地方是 fix 节点：它执行完之后直接走 → code，而不经过任何 gate。
    这时 gate_decision 还是 gate_code 上次写的 "fix"，
    但没关系——code 执行完之后会立刻走 gate_code，gate_code 会用新的 html 重新评估并覆盖写入新的 gate_decision。
    """

    gate_decision: str  # 当前门禁决策（proceed/retry/fix/block）
