# sinan/harness/orchestrator.py
"""Harness 节点装饰器：契约校验 + 门禁评估 + 产物落库。

对齐参考 page/harness/orchestrator.py:wrap_node。每个被包装的节点执行完后：
1. 按步骤跑输出契约校验，失败追加到 state["contract_errors"]（不阻断）；
2. 跑质量门，报告追加到 state["gate_reports"]；
3. 把 current_step 与 gate_reports 写回 gen_session；
4. analysis / design / verification 三类产物写入 generation_artifact 表。

与参考的差异（记入兼容矩阵）：
- 参考另有 harness_checkpoint 表做双层 checkpoint（MySQL + Redis），
  sinan 没有该表，checkpoint 仍由 LangGraph 的 MemorySaver 承担；
  Step 9 已迁到 artifact_store，大内容通过 LocalStorage 卸载，bos_path 写 storage_uri；
- 参考写 BOS，sinan 使用 LocalStorage（storage_type=local）。
"""
from __future__ import annotations

import json
import logging
from functools import wraps

from sinan.services.artifact_store import artifact_store

from sinan.harness.contracts import ContractValidator
from sinan.harness.gates import GateEngine
from sinan.models.enums import PipelineState
from sinan.services.session_store import session_store

logger = logging.getLogger(__name__)

_contract_validator = ContractValidator()
_gate_engine = GateEngine()

# 节点名 → 流水线步骤
_NODE_TO_STATE: dict[str, PipelineState] = {
    "router": PipelineState.INGESTION,
    "analyst": PipelineState.ANALYSIS,
    "designer": PipelineState.DESIGN,
    "coder": PipelineState.GENERATION,
    "verifier": PipelineState.VALIDATION,
}

# 步骤 → (artifact_type, state 键)
_ARTIFACT_MAP: dict[PipelineState, tuple[str, str]] = {
    PipelineState.ANALYSIS: ("analysis", "analysis_output"),
    PipelineState.DESIGN: ("design", "design_doc"),
    PipelineState.VALIDATION: ("verification", "verification_result"),
}


def wrap_node(node_fn, node_name: str):
    """给节点函数套上 harness：契约 + 门禁 + 产物落库。"""

    @wraps(node_fn)
    async def wrapped(state: dict) -> dict:
        result = await node_fn(state)

        step = _NODE_TO_STATE.get(node_name)
        if step is None:
            return result

        violation = _validate_contract(step, result)
        if violation:
            errors = list(state.get("contract_errors") or [])
            errors.append(violation)
            result["contract_errors"] = errors

        report = await _evaluate_gate(step, result, state)
        if report:
            reports = list(state.get("gate_reports") or [])
            reports.append(report)
            result["gate_reports"] = reports

        await _persist(state, step, result)
        return result

    return wrapped


def _validate_contract(step: PipelineState, result: dict) -> dict | None:
    """跑输出契约校验，返回违规 dict 或 None。"""
    getters = {
        PipelineState.INGESTION: lambda: result.get("intent"),
        PipelineState.ANALYSIS: lambda: result.get("analysis_output"),
        PipelineState.DESIGN: lambda: result.get("design_doc"),
        PipelineState.GENERATION: lambda: (
            {"files": result.get("code_files") or [],
             "entry_point": "index.html", "dependencies": []}
            if result.get("code") else None
        ),
        PipelineState.VALIDATION: lambda: result.get("verification_result"),
    }
    getter = getters.get(step)
    if not getter:
        return None
    data = getter()
    if not isinstance(data, dict) or not data:
        return None
    validation = _contract_validator.validate_output(step, data)
    if _contract_validator.is_violation(validation):
        return {"step": step.value, "errors": validation.errors}
    return None


async def _evaluate_gate(step: PipelineState, result: dict, state: dict) -> dict | None:
    """把 state 里的产出适配成门禁需要的对象，返回门禁报告。"""

    class _Obj:
        pass

    obj = _Obj()
    if step == PipelineState.INGESTION:
        if result.get("intent"):
            obj.requirement = (type("R", (), {"title": "x", "features": ["x"]})()
                               if result.get("intent") else None)
    elif step == PipelineState.ANALYSIS:
        analysis = result.get("analysis_output") or {}
        obj.confidence_score = analysis.get("confidence_score", 0)
        obj.confirmation_digest = analysis.get("confirmation_digest", "")
    elif step == PipelineState.DESIGN:
        design = result.get("design_doc") or {}
        obj.layout = design.get("layout")
        obj.component_tree = design.get("component_tree")
    elif step == PipelineState.GENERATION:
        files = result.get("code_files") or []
        obj.files = [type("F", (), {"path": f.get("path")})() for f in files]
        obj.entry_point = "index.html"
    elif step == PipelineState.VALIDATION:
        obj.quality_score = (result.get("verification_result") or {}).get("quality_score", 0)
    else:
        return None

    gate_result = await _gate_engine.evaluate(step, obj, {"state": state})
    return gate_result.to_report(step, {"state": state})


async def _persist(state: dict, step: PipelineState, result: dict) -> None:
    """写 session 的 current_step / gate_reports，并落 artifact。异常只记日志。"""
    session_id = state.get("session_id") or ""
    if not session_id:
        return

    reports = result.get("gate_reports") or state.get("gate_reports")
    update_kwargs: dict = {
        "current_step": step.value,
        "pipeline_state": result.get("pipeline_state") or step.value,
    }
    if reports:
        # gen_session.gate_reports 是 Text 列，存 JSON 文本
        update_kwargs["gate_reports"] = json.dumps(reports, ensure_ascii=False)
    try:
        await session_store.update(session_id, **update_kwargs)
    except Exception:
        logger.exception("harness: session 更新失败 session_id=%s", session_id)

    entry = _ARTIFACT_MAP.get(step)
    if not entry:
        return
    artifact_type, key = entry
    content = result.get(key)
    if not isinstance(content, dict) or not content:
        return
    marker = state.get("marker")
    try:
        await artifact_store.save_artifact(
            session_id, artifact_type, content, marker=marker,
        )
    except Exception:
        logger.exception("harness: artifact 写入失败 session_id=%s type=%s",
                         session_id, artifact_type)

