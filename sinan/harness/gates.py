# sinan/harness/gates.py
"""质量门引擎：六个门，按 PipelineState 分派。

对齐参考 page/harness/gates.py 的门定义、阈值和 GateResult 字段，
并按实施计划 7.6 额外收敛一个 decision 字段：
    passed and not requires_user           → proceed
    requires_user                          → wait_user
    未通过且是 VALIDATION/GENERATION 步骤   → fix
    未通过且已达最大修复轮次                 → block
    其他未通过                              → retry

与 Step 6 之前的差异：旧 GateEngine.evaluate(step: str, state: dict) 按
_gate_{step} 方法名分派，且门禁本身决定图的走向（gate_* 是独立节点）。
现在门禁不再决定路由——路由由 graph 的条件边读 verification_result 决定，
门禁只产出报告，与参考一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sinan.config.settings import settings
from sinan.models.enums import GateDecision, PipelineState


@dataclass
class GateCheck:
    """门内的单项检查。"""

    name: str
    passed: bool
    score: float = 1.0
    message: str = ""


@dataclass
class GateResult:
    """门禁评估结果。"""

    gate_name: str
    passed: bool
    score: float = 0.0
    checks: list[GateCheck] = field(default_factory=list)
    requires_user: bool = False
    user_prompt: str | None = None
    auto_confirmed: bool = False

    def decision(self, step: PipelineState, context: dict | None = None) -> str:
        """把 passed/requires_user 收敛成实施计划要求的 decision 字符串。"""
        if self.requires_user:
            return GateDecision.WAIT_USER.value
        if self.passed:
            return GateDecision.PROCEED.value
        state = (context or {}).get("state") or {}
        fix_round = state.get("fix_round", 0)
        max_rounds = state.get("max_fix_rounds", settings.max_fix_rounds)
        if step in (PipelineState.GENERATION, PipelineState.VALIDATION):
            return (GateDecision.BLOCK.value if fix_round >= max_rounds
                    else GateDecision.FIX.value)
        return GateDecision.RETRY.value

    def to_report(self, step: PipelineState, context: dict | None = None) -> dict:
        """落库/上报用的门禁报告（实施计划 7.6 指定字段）。"""
        return {
            "gate": self.gate_name,
            "step": step.value,
            "decision": self.decision(step, context),
            "passed": self.passed,
            "score": self.score,
            "issues": [c.message for c in self.checks if not c.passed and c.message],
            "auto_confirmed": self.auto_confirmed,
            "requires_user": self.requires_user,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        }


class GateEngine:
    """按流水线步骤评估质量门。"""

    async def evaluate(self, step: PipelineState, output: Any, context: dict) -> GateResult:
        evaluator = self._get_evaluator(step)
        if evaluator is None:
            return GateResult(gate_name=f"gate_{step.value}", passed=True, score=1.0)
        return await evaluator(output, context)

    def _get_evaluator(self, step: PipelineState):
        return {
            PipelineState.INGESTION: self._gate_schema_validation,
            PipelineState.ANALYSIS: self._gate_user_confirmation,
            PipelineState.DESIGN: self._gate_design_completeness,
            PipelineState.GENERATION: self._gate_syntax_integrity,
            PipelineState.VALIDATION: self._gate_quality_threshold,
            PipelineState.PREVIEW: self._gate_render_success,
        }.get(step)

    async def _gate_schema_validation(self, output: Any, context: dict) -> GateResult:
        """门 1：摄取后的 schema 校验。"""
        req = getattr(output, "requirement", None)
        ok = bool(req and getattr(req, "title", None) and getattr(req, "features", None))
        checks = [GateCheck(name="requirement_complete", passed=ok,
                            message="" if ok else "Requirement incomplete")]
        return GateResult(gate_name="schema_validation", passed=ok,
                          score=1.0 if ok else 0.0, checks=checks)

    async def _gate_user_confirmation(self, output: Any, context: dict) -> GateResult:
        """门 2：用户确认门。置信度 >= 阈值则自动确认。"""
        confidence = float(getattr(output, "confidence_score", 0.0) or 0.0)
        if confidence >= settings.auto_confirm_threshold:
            return GateResult(gate_name="user_confirmation", passed=True,
                              score=confidence, auto_confirmed=True)
        return GateResult(
            gate_name="user_confirmation",
            passed=False,
            score=confidence,
            requires_user=True,
            user_prompt=getattr(output, "confirmation_digest", ""),
        )

    async def _gate_design_completeness(self, output: Any, context: dict) -> GateResult:
        """门 3：设计完整性。"""
        has_layout = bool(getattr(output, "layout", None))
        has_tree = bool(getattr(output, "component_tree", None))
        checks = [
            GateCheck(name="layout_defined", passed=has_layout,
                      message="" if has_layout else "No layout"),
            GateCheck(name="component_tree_defined", passed=has_tree,
                      message="" if has_tree else "No component tree"),
        ]
        passed = all(c.passed for c in checks)
        return GateResult(gate_name="design_completeness", passed=passed,
                          score=1.0 if passed else 0.5, checks=checks)

    async def _gate_syntax_integrity(self, output: Any, context: dict) -> GateResult:
        """门 4：代码文件与入口完整性。"""
        files = getattr(output, "files", []) or []
        if not files:
            checks = [GateCheck(name="files_exist", passed=False, message="No files generated")]
            return GateResult(gate_name="syntax_integrity", passed=False, score=0.0, checks=checks)
        entry = getattr(output, "entry_point", "")
        has_entry = any(getattr(f, "path", None) == entry for f in files)
        checks = [
            GateCheck(name="files_exist", passed=True),
            GateCheck(name="entry_point_valid", passed=has_entry,
                      message="" if has_entry else f"Entry '{entry}' not found"),
        ]
        passed = all(c.passed for c in checks)
        return GateResult(gate_name="syntax_integrity", passed=passed,
                          score=1.0 if passed else 0.0, checks=checks)

    async def _gate_quality_threshold(self, output: Any, context: dict) -> GateResult:
        """门 5：质量分阈值（参考硬编码 0.8，这里走 settings.quality_threshold）。"""
        score = float(getattr(output, "quality_score", 0.0) or 0.0)
        return GateResult(gate_name="quality_threshold",
                          passed=score >= settings.quality_threshold, score=score)

    async def _gate_render_success(self, output: Any, context: dict) -> GateResult:
        """门 6：渲染成功。渲染质量已在 verifier 的 RenderValidator 里计入 quality_score，
        这里是占位，等有独立 PREVIEW 节点后再实现（参考同样是占位）。"""
        return GateResult(gate_name="render_success", passed=True, score=1.0)