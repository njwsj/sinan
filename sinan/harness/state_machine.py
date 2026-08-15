# sinan/harness/state_machine.py
from enum import Enum


class PipelineState(Enum):
    """流水线的所有合法状态。
    INIT → ANALYSIS → DESIGN → GENERATION → VALIDATION → HOST → COMPLETED
                     ↑ (回退重分析)          ↓ (修复循环)
                  ANALYSIS               FIX → GENERATION
                                              ↓ (超限失败)
                                           FAILED
    """
    INIT = "init"             # 初始状态，流水线刚启动
    ANALYSIS = "analysis"     # Analyzer Agent：解析用户需求
    DESIGN = "design"         # Designer Agent：生成页面设计方案
    GENERATION = "generation" # Coder Agent：生成 HTML 代码
    VALIDATION = "validation" # Verifier Agent：校验生成结果
    FIX = "fix"               # Fixer Agent：修复不合格的 HTML
    HOST = "host"             # 发布/托管生成的页面
    COMPLETED = "completed"   # 终态：流水线成功结束
    FAILED = "failed"         # 终态：流水线失败退出


# 状态转移表：定义每个状态允许跳转到哪些后续状态。
# 未在此表中列出的跳转均视为非法。
# 流转路径示意：
#   INIT → ANALYSIS → DESIGN → GENERATION → VALIDATION → HOST → COMPLETED
#                ↑        ↓ (重新设计)         ↓ (修复)
#             FAILED    ANALYSIS             FIX → GENERATION
TRANSITION_TABLE: dict[PipelineState, list[PipelineState]] = {
    PipelineState.INIT:       [PipelineState.ANALYSIS],
    PipelineState.ANALYSIS:   [PipelineState.DESIGN, PipelineState.FAILED],
    PipelineState.DESIGN:     [PipelineState.GENERATION, PipelineState.ANALYSIS],  # 设计不通过可回退重新分析
    PipelineState.GENERATION: [PipelineState.VALIDATION],
    PipelineState.VALIDATION: [PipelineState.HOST, PipelineState.FIX, PipelineState.FAILED],
    PipelineState.FIX:        [PipelineState.GENERATION],  # 修复后重新生成
    PipelineState.HOST:       [PipelineState.COMPLETED, PipelineState.FAILED],
    PipelineState.COMPLETED:  [],  # 终态，无后续跳转
    PipelineState.FAILED:     [],  # 终态，无后续跳转
}


def can_transition(from_state: PipelineState, to_state: PipelineState) -> bool:
    """判断从 from_state 跳转到 to_state 是否合法。"""
    return to_state in TRANSITION_TABLE.get(from_state, [])