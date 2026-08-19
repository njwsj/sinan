# sinan/agents/verifier.py
"""Verifier Agent：跑五个维度的校验器，产出结构化 verification_result。

对齐参考 page/agents/verifier.py：
- issues 是 ValidationIssue 列表；
- passed = 不存在 P0/P1（P2 不阻断）；
- quality_score = compute_quality_score(issues)；
- check_results 按 _CHECK_POINTS 逐检查点给出 passed 与命中的 issues。

与 Step 6 之前的差异：不再返回 verified/verify_message，也不再直接调用
BrowserValidator（渲染校验收敛进 harness/validators/render.py）。
"""
from __future__ import annotations

from sinan.agents.state import GenerationState
from sinan.harness.validators.data import DataValidator
from sinan.harness.validators.render import RenderValidator
from sinan.harness.validators.requirement import RequirementValidator
from sinan.harness.validators.syntax import SyntaxValidator
from sinan.harness.validators.template import TemplateValidator
from sinan.models.contracts import compute_quality_score
from sinan.models.enums import PipelineState

_CHECK_POINTS = {
    "requirement": [
        {"id": "req_basic_structure", "name": "基本页面结构", "description": "页面包含完整的HTML结构（body标签等）"},
        {"id": "req_features", "name": "核心功能实现", "description": "需求分析中要求的组件/功能在页面中实现"},
        {"id": "req_acceptance", "name": "验收标准满足", "description": "满足需求分析中的关键验收标准"},
    ],
    "template": [
        {"id": "tpl_style", "name": "样式风格一致", "description": "页面CSS样式与模板保持一致"},
        {"id": "tpl_layout", "name": "布局结构一致", "description": "页面布局方式与模板保持一致"},
        {"id": "tpl_color", "name": "配色方案一致", "description": "页面配色与模板主色保持一致"},
    ],
    "data": [
        {"id": "data_column_match", "name": "数据字段匹配", "description": "页面数据字段与用户上传文件的列名一致"},
        {"id": "data_no_hardcode", "name": "数据非硬编码", "description": "指标数值从数据计算得出，非硬编码"},
        {"id": "data_raw_integrity", "name": "数据来源完整性", "description": "页面数据来源于用户选择的数据源"},
    ],
    "syntax": [
        {"id": "syntax_js_error", "name": "JS 语法正确", "description": "script 块不包含语法错误，可被 Node.js 解析"},
    ],
}


class VerifierAgent:
    """五维度校验，不调用 LLM。"""

    async def run(self, state: GenerationState) -> dict:
        code = state.get("code") or ""
        analysis_output = state.get("analysis_output")
        design_doc = state.get("design_doc")
        attachments = state.get("attachments")
        template_code = state.get("template_code")

        issues = []
        issues.extend(RequirementValidator().validate(code, analysis_output, design_doc))
        issues.extend(TemplateValidator().validate(code, template_code, design_doc))
        issues.extend(DataValidator().validate(code, design_doc, attachments))
        issues.extend(SyntaxValidator().validate(code))
        issues.extend(await RenderValidator().validate(code))

        blocking = [i for i in issues if i.severity in ("P0", "P1")]
        score = compute_quality_score(issues)

        check_results = []
        for category, checks in _CHECK_POINTS.items():
            for check in checks:
                matched = [i.model_dump() for i in issues if i.issue_id.startswith(check["id"])]
                check_results.append({
                    "category": category,
                    "id": check["id"],
                    "name": check["name"],
                    "description": check["description"],
                    "passed": not matched,
                    "issues": matched,
                })

        result = {
            "passed": len(blocking) == 0,
            "issues": [i.model_dump() for i in issues],
            "blocking_count": len(blocking),
            "quality_score": score,
            "check_results": check_results,
            "summary": {
                "total_checks": len(check_results),
                "passed_checks": sum(1 for c in check_results if c["passed"]),
                "failed_checks": sum(1 for c in check_results if not c["passed"]),
            },
        }
        return {
            "verification_result": result,
            "status": "completed" if result["passed"] else "fixing",
            "pipeline_state": PipelineState.VALIDATION.value,
        }