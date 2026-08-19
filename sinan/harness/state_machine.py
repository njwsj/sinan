# sinan/harness/state_machine.py
"""流水线状态机：11 态 + 带条件的转移表。

对齐参考 page/harness/state_machine.py。与 Step 6 之前的差异：
- 状态取值改用 models/enums.PipelineState（不再在本文件另定义一份 Enum，
  原先本文件的 HOST/FIX/COMPLETED 与 models/enums 的 preview/user_review/delivered 是两套，
  这是 Step 6 遗留的双份定义问题，本 Step 收敛掉）；
- 转移表带 condition，同一对 (from, to) 可由不同条件触发。

诚实标注：参考项目的 PipelineStateMachine 同样没有被 LangGraph 图接进运行时
（图里的 pipeline_state 是各节点直接写字符串），因此实施计划 7.5 所说的
"运行时唯一状态转移来源" 参考侧也未实现。sinan 本 Step 只做到与参考同构，
把 "运行时强校验" 作为两边共同缺口留给 Step 15。
"""
from __future__ import annotations

from sinan.models.enums import PipelineState

# (from_state, to_state, condition)；condition 为 None 表示无条件
TRANSITION_TABLE: list[tuple[PipelineState, PipelineState, str | None]] = [
    (PipelineState.INIT, PipelineState.INGESTION, None),
    (PipelineState.INGESTION, PipelineState.ANALYSIS, None),
    (PipelineState.ANALYSIS, PipelineState.USER_CONFIRM, None),
    (PipelineState.USER_CONFIRM, PipelineState.DESIGN, "user_confirmed"),
    (PipelineState.USER_CONFIRM, PipelineState.ANALYSIS, "user_rejected"),
    (PipelineState.DESIGN, PipelineState.GENERATION, None),
    (PipelineState.GENERATION, PipelineState.VALIDATION, None),
    (PipelineState.VALIDATION, PipelineState.PREVIEW, "validation_passed"),
    (PipelineState.VALIDATION, PipelineState.GENERATION, "repair_needed"),
    (PipelineState.VALIDATION, PipelineState.FAILED, "repair_exhausted"),
    (PipelineState.PREVIEW, PipelineState.USER_REVIEW, None),
    (PipelineState.USER_REVIEW, PipelineState.DESIGN, "change_structural"),
    (PipelineState.USER_REVIEW, PipelineState.GENERATION, "change_partial"),
    (PipelineState.USER_REVIEW, PipelineState.DELIVERED, "user_accepted"),
]


class InvalidTransitionError(Exception):
    """非法状态转移。"""


class PipelineStateMachine:
    """强制校验状态转移合法性。"""

    def __init__(self, initial: PipelineState = PipelineState.INIT):
        self._state = initial
        self._history: list[tuple[PipelineState, PipelineState, str | None]] = []

    @property
    def state(self) -> PipelineState:
        return self._state

    @property
    def history(self) -> list[tuple[PipelineState, PipelineState, str | None]]:
        return self._history.copy()

    def can_transition(self, target: PipelineState, condition: str | None = None) -> bool:
        for from_s, to_s, cond in TRANSITION_TABLE:
            if from_s == self._state and to_s == target:
                if cond is None or cond == condition:
                    return True
        return False

    def transition(self, target: PipelineState, condition: str | None = None) -> None:
        if not self.can_transition(target, condition):
            raise InvalidTransitionError(
                f"Invalid transition: {self._state.value} -> {target.value} (condition={condition})"
            )
        self._history.append((self._state, target, condition))
        self._state = target

    def get_valid_targets(self) -> list[tuple[PipelineState, str | None]]:
        return [(to_s, cond) for from_s, to_s, cond in TRANSITION_TABLE if from_s == self._state]


def can_transition(
    from_state: PipelineState, to_state: PipelineState, condition: str | None = None
) -> bool:
    """无状态的转移合法性判断（保留旧函数名，签名新增 condition）。"""
    return PipelineStateMachine(from_state).can_transition(to_state, condition)