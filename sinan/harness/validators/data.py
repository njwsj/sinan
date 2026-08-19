# sinan/harness/validators/data.py
"""数据一致性校验：页面数据必须来自用户输入，而不是 mock/硬编码。

对齐参考 page/harness/validators/data.py。三项检查：
1. 上传了附件但代码里完全不引用任何列名 → P1；
2. innerHTML/textContent 直接写死 3 位以上数字 → P1；
3. 模板字符串 ${...} 引用了未声明变量（典型是大小写不一致）→ P0。
"""
from __future__ import annotations

import re

from sinan.models.contracts import ValidationIssue
from sinan.models.enums import IssueSeverity

_JS_GLOBALS = {
    "undefined", "null", "true", "false", "NaN", "Infinity",
    "Math", "JSON", "Object", "Array", "String", "Number",
    "Boolean", "Date", "console", "window", "document",
    "parseInt", "parseFloat", "isNaN", "isFinite",
    "row", "item", "index", "el", "e", "event", "params",
    "echarts", "formatWan", "formatPercent",
}


class DataValidator:
    """校验页面数据来源与变量引用正确性。"""

    def validate(
        self,
        code: str,
        design_doc: dict | None = None,
        attachments: list[dict] | None = None,
    ) -> list[ValidationIssue]:
        if not code or len(code.strip()) < 50:
            return []
        issues: list[ValidationIssue] = []
        if attachments:
            issues.extend(self._check_data_source(code, attachments))
        issues.extend(self._check_hardcoded_data(code))
        issues.extend(self._check_template_literal_vars(code))
        return issues

    def _check_data_source(self, code: str, attachments: list[dict]) -> list[ValidationIssue]:
        expected: list[str] = []
        for att in attachments or []:
            parsed = att.get("parsed") or {}
            cols = att.get("columns") or parsed.get("columns") or []
            for c in cols:
                if isinstance(c, str) and c not in expected:
                    expected.append(c)
        if not expected:
            return []

        data_blocks = re.findall(
            r"(?:rawData|const\s+\w*[Dd]ata\w*|let\s+\w*[Dd]ata\w*|var\s+\w*[Dd]ata\w*)\s*=\s*"
            r"\[(\s*\{.*?\}\s*,?\s*)+\]",
            code, re.DOTALL,
        )
        if not data_blocks:
            data_blocks = re.findall(r"\[\s*\{\s*[\"']?\w+[\"']?\s*:", code, re.DOTALL)
        if data_blocks:
            return []

        code_lower = code.lower()
        if not any(c.lower() in code_lower for c in expected):
            return [ValidationIssue(
                issue_id="data_no_source_block",
                severity=IssueSeverity.P1.value,
                category="data",
                description="用户上传了数据文件，但页面中未引用任何上传数据的字段",
                suggestion="页面数据应来源于用户上传的文件，需引用上传数据的字段名",
            )]
        return []

    def _check_hardcoded_data(self, code: str) -> list[ValidationIssue]:
        hardcoded = re.findall(r"(?:innerHTML|textContent)\s*=\s*[\"'](\d{3,})[\"']", code)
        if not hardcoded:
            return []
        return [ValidationIssue(
            issue_id="data_hardcoded_values",
            severity=IssueSeverity.P1.value,
            category="data",
            description=f"发现疑似硬编码数值: {hardcoded[:3]}，应从数据中计算得出",
            suggestion="指标数值应从 rawData 中计算得出，不应硬编码结果",
        )]

    def _check_template_literal_vars(self, code: str) -> list[ValidationIssue]:
        script_blocks = re.findall(r"<script[^>]*>(.*?)</script>", code, re.DOTALL | re.IGNORECASE)
        if not script_blocks:
            return []
        js_code = "\n".join(script_blocks)

        declared: set[str] = set()
        for m in re.finditer(r"\b(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)", js_code):
            declared.add(m.group(1))
        for m in re.finditer(r"\bfunction\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", js_code):
            declared.add(m.group(1))
        for m in re.finditer(r"\bfunction\s*\w*\s*\(([^)]*)\)", js_code):
            for param in m.group(1).split(","):
                param = param.split("=")[0].strip()
                if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", param):
                    declared.add(param)
        for m in re.finditer(r"(?:\(([^)]*)\)|([A-Za-z_$][A-Za-z0-9_$]*))\s*=>", js_code):
            params_str = m.group(1) if m.group(1) is not None else m.group(2)
            for param in params_str.split(","):
                param = re.sub(r"[{}\[\]()]", "", param).split("=")[0].strip()
                if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", param):
                    declared.add(param)

        refs: list[str] = []
        for tl in re.finditer(r"`([\s\S]*?)`", js_code):
            for ref in re.finditer(r"\$\{([A-Za-z_$][A-Za-z0-9_$]*)", tl.group()):
                refs.append(ref.group(1))

        undefined = [r for r in refs if r not in declared and r not in _JS_GLOBALS]
        if not undefined:
            return []
        return [ValidationIssue(
            issue_id="data_template_literal_undefined_var",
            severity=IssueSeverity.P0.value,
            category="data",
            description=(
                f"模板字符串中引用了未声明的变量: {list(dict.fromkeys(undefined))[:5]}，"
                "可能是变量名大小写不匹配"
            ),
            suggestion="检查模板字符串中 ${...} 引用的变量名，确保与声明的变量名大小写完全一致",
        )]