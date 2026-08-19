# sinan/harness/validators/template.py
"""模板一致性校验：仅在 state["template_code"] 存在时生效（Step 11 起才有真实模板）。

对齐参考 page/harness/validators/template.py，检查三项：
CSS 变量保留率（丢失过半报 P1）、布局模式一致（Grid→无 Grid/Flex 报 P1）、
主色调是否完全无交集（报 P1）；圆角与字体差异只报 P2。
"""
from __future__ import annotations

import re

from sinan.models.contracts import ValidationIssue
from sinan.models.enums import IssueSeverity

_SECTION_ATTR_RE = (
    r'(?:class|id)\s*=\s*["\']'
    r'([^"\']*(?:section|area|region|zone|panel|container|card)[^"\']*)'
    r'["\']'
)


class TemplateValidator:
    """校验生成代码与模板的视觉/结构一致性。"""

    def validate(
        self,
        code: str,
        template_code: str | None = None,
        design_doc: dict | None = None,
    ) -> list[ValidationIssue]:
        if not template_code:
            return []
        if not code or len(code.strip()) < 50:
            return [ValidationIssue(
                issue_id="tpl_empty_code",
                severity=IssueSeverity.P0.value,
                category="template",
                description="页面代码为空或过短，无法与模板比较",
            )]

        issues: list[ValidationIssue] = []
        issues.extend(self._check_style_consistency(code, template_code))
        issues.extend(self._check_layout_consistency(code, template_code))
        issues.extend(self._check_color_consistency(code, template_code))
        return issues

    def _check_style_consistency(self, code: str, template_code: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        tpl_vars = set(re.findall(r"--([\w-]+)\s*:", template_code))
        if tpl_vars:
            code_vars = set(re.findall(r"--([\w-]+)\s*:", code))
            missing = tpl_vars - code_vars
            if len(missing) > len(tpl_vars) * 0.5:
                issues.append(ValidationIssue(
                    issue_id="tpl_css_vars_missing",
                    severity=IssueSeverity.P1.value,
                    category="template",
                    description=(
                        f"模板定义了 {len(tpl_vars)} 个 CSS 变量，"
                        f"页面仅保留了 {len(tpl_vars) - len(missing)} 个"
                    ),
                    suggestion="保留模板中的 CSS 变量定义，确保视觉风格一致",
                ))

        tpl_radii = set(re.findall(r"border-radius\s*:\s*([^\s;]+)", template_code))
        code_radii = set(re.findall(r"border-radius\s*:\s*([^\s;]+)", code))
        if tpl_radii and not tpl_radii.intersection(code_radii):
            issues.append(ValidationIssue(
                issue_id="tpl_border_radius_mismatch",
                severity=IssueSeverity.P2.value,
                category="template",
                description=f"模板使用圆角 {tpl_radii}，但页面使用了不同的圆角值 {code_radii}",
                suggestion="保持与模板一致的 border-radius 值",
            ))

        if re.findall(r"font-family\s*:\s*([^;]+)", template_code) and not re.findall(
            r"font-family\s*:\s*([^;]+)", code
        ):
            issues.append(ValidationIssue(
                issue_id="tpl_font_missing",
                severity=IssueSeverity.P2.value,
                category="template",
                description="模板定义了 font-family，但页面未使用",
                suggestion="保留模板的 font-family 设置",
            ))
        return issues

    def _check_layout_consistency(self, code: str, template_code: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        tpl_has_grid = bool(re.search(r"display\s*:\s*grid|grid-template", template_code))
        code_has_grid = bool(re.search(r"display\s*:\s*grid|grid-template", code))
        code_has_flex = bool(re.search(r"display\s*:\s*flex", code))

        if tpl_has_grid and not code_has_grid and not code_has_flex:
            issues.append(ValidationIssue(
                issue_id="tpl_layout_mode_mismatch",
                severity=IssueSeverity.P1.value,
                category="template",
                description="模板使用 Grid 布局，但页面未使用 Grid 或 Flex 布局",
                suggestion="保持与模板一致的布局方式",
            ))

        tpl_sections = re.findall(_SECTION_ATTR_RE, template_code, re.IGNORECASE)
        if tpl_sections:
            code_sections = re.findall(_SECTION_ATTR_RE, code, re.IGNORECASE)
            if not code_sections and len(tpl_sections) >= 2:
                issues.append(ValidationIssue(
                    issue_id="tpl_sections_missing",
                    severity=IssueSeverity.P2.value,
                    category="template",
                    description="模板包含多个结构区域，但页面缺少对应的区域划分",
                    suggestion="保持与模板一致的页面结构区域划分",
                ))
        return issues

    def _check_color_consistency(self, code: str, template_code: str) -> list[ValidationIssue]:
        trivial = {"fff", "FFF", "ffffff", "FFFFFF", "000", "000000", "00000000"}
        tpl_colors = set(re.findall(r"#([0-9a-fA-F]{3,8})(?!\w)", template_code)) - trivial
        code_colors = set(re.findall(r"#([0-9a-fA-F]{3,8})(?!\w)", code)) - trivial

        if tpl_colors and code_colors and not tpl_colors.intersection(code_colors) and len(tpl_colors) >= 2:
            return [ValidationIssue(
                issue_id="tpl_color_palette_mismatch",
                severity=IssueSeverity.P1.value,
                category="template",
                description="页面配色与模板完全不同，未保留任何模板主色",
                suggestion="保留模板的主色调和配色方案，确保视觉风格一致",
            )]
        return []