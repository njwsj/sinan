# sinan/harness/validators/requirement.py
"""需求一致性校验：生成代码是否落实了需求分析里的要求。

对齐参考 page/harness/validators/requirement.py。三块检查：
1. 最小 HTML 结构（缺 body 直接 P0）；
2. 外部图标字体库（内网加载不到字体，图标会退化成英文文字，P0）；
3. 功能覆盖率 < 80% 报 P1；验收标准里的响应式/中文要求报 P1/P2。
"""
from __future__ import annotations

import re

from sinan.models.contracts import ValidationIssue
from sinan.models.enums import IssueSeverity


class RequirementValidator:
    """校验生成代码是否满足分析阶段的需求。"""

    def validate(
        self,
        code: str,
        analysis_output: dict | None = None,
        design_doc: dict | None = None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        if not code or len(code.strip()) < 50:
            issues.append(ValidationIssue(
                issue_id="req_empty_code",
                severity=IssueSeverity.P0.value,
                category="requirement",
                description="页面代码为空或过短，无法满足任何需求",
            ))
            return issues

        issues.extend(self._check_basic_structure(code))
        # 图标字体检查与 analysis_output 无关，始终执行
        issues.extend(self._check_icon_fonts(code))

        if not analysis_output:
            return issues
        content = analysis_output.get("_content", "")
        if not content:
            return issues

        issues.extend(self._check_feature_coverage(code, content, design_doc))
        issues.extend(self._check_acceptance_criteria(code, content))
        return issues

    def _check_basic_structure(self, code: str) -> list[ValidationIssue]:
        if not re.search(r"<body[^>]*>", code, re.IGNORECASE):
            return [ValidationIssue(
                issue_id="req_no_body",
                severity=IssueSeverity.P0.value,
                category="requirement",
                description="页面缺少 <body> 标签，无法正常渲染",
                suggestion="添加完整的 HTML 结构，包含 <body> 标签",
            )]
        return []

    def _check_feature_coverage(
        self, code: str, analysis_content: str, design_doc: dict | None = None
    ) -> list[ValidationIssue]:
        """需求里提到的组件类型是否在代码里出现，覆盖率 < 80% 报 P1。"""
        feature_indicators = {
            "图表": [r"Chart", r"echarts", r"chart", r"<canvas", r"setOption"],
            "表格": [r"<table", r"el-table", r"Table", r"grid"],
            "筛选": [r"select", r"filter", r"Select", r"Filter", r"dropdown"],
            "指标卡": [r"card", r"Card", r"KPI", r"indicator"],
        }
        required: dict[str, bool] = {
            name: False for name in feature_indicators if name in analysis_content
        }

        # component_tree 比文本关键词更精确，优先补充
        if design_doc:
            tree = design_doc.get("component_tree") or {}
            for child in (tree.get("children") or []):
                ctype = child.get("component_type", "")
                if ctype in ("bar_chart", "line_chart", "pie_chart"):
                    required["图表"] = False
                elif ctype == "table":
                    required["表格"] = False
                elif ctype == "filter":
                    required["筛选"] = False
                elif ctype == "number_card":
                    required["指标卡"] = False

        for name, patterns in feature_indicators.items():
            if name not in required:
                continue
            for pattern in patterns:
                if re.search(pattern, code, re.IGNORECASE):
                    required[name] = True
                    break

        missing = [name for name, present in required.items() if not present]
        total = len(required)
        coverage = (total - len(missing)) / total if total else 1.0
        if coverage < 0.8:
            return [ValidationIssue(
                issue_id="req_features_missing",
                severity=IssueSeverity.P1.value,
                category="requirement",
                description=f"功能覆盖率 {coverage:.0%}，未实现功能: {missing}",
                suggestion="确保页面实现了需求分析中提到的所有核心功能组件",
            )]
        return []

    def _check_icon_fonts(self, code: str) -> list[ValidationIssue]:
        """外部图标字体库在内网加载不到，图标会显示成 'signal'、'home' 这类文字。"""
        cdn_patterns = [
            (r'fonts\.googleapis\.com[^"\']*material.{0,30}icon', "Material Icons（Google Fonts CDN）"),
            (r'fonts\.gstatic\.com[^"\']*material', "Material Icons（Google Fonts CDN）"),
            (r'font-awesome[^"\']*\.css', "Font Awesome"),
            (r'fontawesome[^"\']*\.css', "Font Awesome"),
            (r'cdnjs\.cloudflare\.com[^"\']*font-awesome', "Font Awesome（cdnjs CDN）"),
            (r"use\.fontawesome\.com", "Font Awesome"),
            (r'cdn\.jsdelivr\.net[^"\']*bootstrap-icons', "Bootstrap Icons（jsdelivr CDN）"),
            (r'bootstrap-icons[^"\']*\.css', "Bootstrap Icons"),
            (r'ionicons[^"\']*\.css', "Ionicons"),
            (r'unpkg\.com[^"\']*ionicons', "Ionicons（unpkg CDN）"),
            (r'remixicon[^"\']*\.css', "Remix Icon"),
        ]
        class_patterns = [
            (r'class\s*=\s*["\'][^"\']*\bmaterial-icons\b', "Material Icons（class 引用）"),
            (r'class\s*=\s*["\'][^"\']*\bfa\s', "Font Awesome（fa class）"),
            (r'class\s*=\s*["\'][^"\']*\bfas\b', "Font Awesome（fas class）"),
            (r'class\s*=\s*["\'][^"\']*\bfar\b', "Font Awesome（far class）"),
            (r'class\s*=\s*["\'][^"\']*\bfab\b', "Font Awesome（fab class）"),
            (r'class\s*=\s*["\'][^"\']*\bbi-[a-z]', "Bootstrap Icons（bi- class）"),
        ]
        found: list[str] = []
        for pattern, label in cdn_patterns + class_patterns:
            if re.search(pattern, code, re.IGNORECASE) and label not in found:
                found.append(label)

        if not found:
            return []
        return [ValidationIssue(
            issue_id="req_icon_font_cdn",
            severity=IssueSeverity.P0.value,
            category="requirement",
            description=(
                f"使用了外部图标字体库（{', '.join(found)}），"
                "内网环境下字体文件无法加载，图标会显示为英文名称文字"
            ),
            suggestion="移除外部图标字体库的 CDN 引用和 class 使用，改用 SVG inline 或 Unicode emoji",
        )]

    def _check_acceptance_criteria(self, code: str, analysis_content: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        match = re.search(
            r"(?:##\s*六[、.]\s*验收标准|##\s*八[、.]\s*验收标准|##\s*验收标准)(.*?)(?=\n##\s|\n---|\Z)",
            analysis_content, re.DOTALL,
        )
        if not match:
            return issues
        criteria = match.group(1)

        if ("响应式" in criteria or "自适应" in criteria) and "viewport" not in code.lower():
            issues.append(ValidationIssue(
                issue_id="req_no_viewport",
                severity=IssueSeverity.P1.value,
                category="requirement",
                description="验收标准要求响应式，但页面缺少 viewport meta 标签",
                suggestion='添加 <meta name="viewport" content="width=device-width, initial-scale=1">',
            ))
        if ("中文" in criteria or "lang" in criteria.lower()):
            if "<html" in code.lower() and "lang=" not in code[:500].lower():
                issues.append(ValidationIssue(
                    issue_id="req_no_lang",
                    severity=IssueSeverity.P2.value,
                    category="requirement",
                    description="验收标准要求中文页面，但 html 标签缺少 lang 属性",
                    suggestion='添加 lang="zh-CN" 到 html 标签',
                ))
        return issues