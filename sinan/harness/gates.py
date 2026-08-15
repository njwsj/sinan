# sinan/harness/gates.py
import logging
from dataclasses import dataclass, field
from typing import List
from pydantic import ValidationError

from sinan.models.contracts import AnalyzeContract, DesignContract, CodeContract

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    decision: str           # "proceed" | "retry" | "fix" | "block"
    reason: str = ""
    issues: List[str] = field(default_factory=list)


class GateEngine:
    """
    门禁引擎：调用对应步骤的 Contract 做校验，只负责根据结果做路由决策。
    校验规则在 contracts.py 里维护，路由策略在这里维护，两层职责分离。
    """

    def evaluate(self, step: str, state: dict) -> GateResult:
        """
        根据步骤名调用对应的门禁方法。
        getattr(obj, name, default) 是 Python 内置函数，作用是按名字字符串去取对象的属性或方法。

        三个参数：
        obj：要查找的对象，这里是 self（当前 GateEngine 实例）
        name：属性/方法的名字，这里是 f"_gate_{step}" 拼出的字符串
        default：找不到时的返回值，这里是 None
        """
        method = getattr(self, f"_gate_{step}", None)
        if method is None:
            logger.debug("no gate defined for step %s, proceeding", step)
            return GateResult(decision="proceed")
        return method(state)

    def _gate_analyze(self, state: dict) -> GateResult:
        try:
            contract = AnalyzeContract(requirements=state.get("requirements", ""))
        except ValidationError as e:
            issues = [err["msg"] for err in e.errors()]
            return GateResult(decision="retry", reason="需求分析格式校验失败", issues=issues)
        """业务内容校验，返回错误列表（空列表 = 通过）。"""
        errors = contract.validate_content()
        if errors:
            return GateResult(decision="retry", reason="需求分析内容校验失败", issues=errors)
        return GateResult(decision="proceed")

    def _gate_design(self, state: dict) -> GateResult:
        try:
            contract = DesignContract(design=state.get("design", ""))
        except ValidationError as e:
            issues = [err["msg"] for err in e.errors()]
            return GateResult(decision="retry", reason="设计方案格式校验失败", issues=issues)

        errors = contract.validate_content()
        if errors:
            return GateResult(decision="retry", reason="设计方案内容校验失败", issues=errors)
        return GateResult(decision="proceed")

    def _gate_code(self, state: dict) -> GateResult:
        try:
            contract = CodeContract(html=state.get("html", ""))
        except ValidationError as e:
            issues = [err["msg"] for err in e.errors()]
            iteration = state.get("iteration", 0)
            if iteration >= state.get("max_iterations", 3):
                return GateResult(decision="block", reason="超过最大修复次数", issues=issues)
            return GateResult(decision="fix", reason="HTML 格式校验失败", issues=issues)

        errors = contract.validate_content()
        if errors:
            iteration = state.get("iteration", 0)
            if iteration >= state.get("max_iterations", 3):
                return GateResult(decision="block", reason="超过最大修复次数", issues=errors)
            return GateResult(decision="fix", reason="HTML 结构不合格", issues=errors)
        return GateResult(decision="proceed")

    def _gate_verify(self, state: dict) -> GateResult:
        if state.get("verified"):
            return GateResult(decision="proceed")
        iteration = state.get("iteration", 0)
        max_iter = state.get("max_iterations", 3)
        if iteration >= max_iter:
            return GateResult(
                decision="block",
                reason=f"验证失败且已达最大迭代次数 {max_iter}",
                issues=[state.get("verify_message", "未知错误")],
            )
        return GateResult(
            decision="retry",
            reason="验证未通过，进入修复循环",
            issues=[state.get("verify_message", "")],
        )