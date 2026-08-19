# sinan/harness/contracts.py
"""契约校验器：按 PipelineState 取输出契约做校验。

对齐参考 page/harness/contracts.py。校验失败返回 ContractViolation 而不抛异常，
由 orchestrator 写进 state["contract_errors"]，不阻断流水线。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from sinan.models.contracts import (
    AnalysisOutput,
    DesignOutput,
    GenerationOutput,
    IngestionOutput,
    ValidationOutput,
)
from sinan.models.enums import PipelineState


class ContractViolation(BaseModel):
    """契约违规记录。direction 固定为 output（当前只校验输出）。"""

    step: str
    direction: str
    errors: list[dict]


OUTPUT_CONTRACTS: dict[PipelineState, type[BaseModel]] = {
    PipelineState.INGESTION: IngestionOutput,
    PipelineState.ANALYSIS: AnalysisOutput,
    PipelineState.DESIGN: DesignOutput,
    PipelineState.GENERATION: GenerationOutput,
    PipelineState.VALIDATION: ValidationOutput,
}


class ContractValidator:
    """按步骤校验输出数据。"""

    def validate_output(self, step: PipelineState, data: dict[str, Any]) -> BaseModel | ContractViolation:
        contract_cls = OUTPUT_CONTRACTS.get(step)
        if contract_cls is None:
            return ContractViolation(step=step.value, direction="output",
                                     errors=[{"msg": "No contract defined"}])
        try:
            return contract_cls.model_validate(data)
        except ValidationError as e:
            return ContractViolation(step=step.value, direction="output", errors=list(e.errors()))

    def is_violation(self, result: Any) -> bool:
        return isinstance(result, ContractViolation)