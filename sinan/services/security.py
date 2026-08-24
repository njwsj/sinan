# sinan/services/security.py
"""页面安全扫描服务。

对齐参考 page/services/security.py，在 RequirementValidator 基础上：
- 追加危险脚本模式扫描（eval/document.write/data: URI）
- ZIP 条目路径安全校验（路径穿越、绝对路径、扩展名、单文件大小）

Step 10 新增；hosting.py 和 upload 路由均可复用。
"""
from __future__ import annotations

import re

from sinan.harness.validators.requirement import RequirementValidator
from sinan.models.contracts import ValidationIssue
from sinan.models.enums import IssueSeverity

_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\beval\s*\(", "eval() 调用"),
    (r"document\.write\s*\(", "document.write() 调用"),
    (r"data:\s*text/html", "data: URI HTML 注入"),
    (r'javascript:\s*[^\s"\'<>]', "javascript: URI"),
]

_ALLOWED_EXTENSIONS = {
    ".html", ".htm", ".css", ".js", ".json",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
    ".txt", ".md",
}

_MAX_SINGLE_FILE_SIZE = 2 * 1024 * 1024   # 2MB
_MAX_TOTAL_SIZE       = 10 * 1024 * 1024  # 10MB
_MAX_FILE_COUNT       = 100


class SecurityService:
    """HTML/ZIP 安全扫描服务。"""

    def __init__(self) -> None:
        self._req_validator = RequirementValidator()

    def scan(self, code: str) -> dict:
        """扫描 HTML 字符串，返回报告。

        返回格式::
            passed: bool
            issues: list[dict]
            total_issues: int
            blocking_issues: int   # P0/P1 数量
        """
        issues: list[ValidationIssue] = list(self._req_validator.validate(code))
        for pattern, label in _DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(ValidationIssue(
                    issue_id=f"sec_{re.sub(r'[^a-z0-9]', '_', label.lower())[:24]}",
                    severity=IssueSeverity.P1.value,
                    category="security",
                    description=f"检测到危险代码模式：{label}",
                    suggestion="移除或替换该代码片段",
                ))
        passed = not any(i.severity in ("P0", "P1") for i in issues)
        return {
            "passed": passed,
            "issues": [i.model_dump() for i in issues],
            "total_issues": len(issues),
            "blocking_issues": sum(1 for i in issues if i.severity in ("P0", "P1")),
        }

    def validate_zip_entry(self, name: str, file_size: int) -> str | None:
        """校验 ZIP 条目，返回错误描述，None 表示合法。"""
        if name.startswith("/"):
            return f"绝对路径被拒绝: {name}"
        if ".." in name:
            return f"路径穿越被拒绝: {name}"
        if file_size > _MAX_SINGLE_FILE_SIZE:
            return f"单文件超限 ({file_size} > {_MAX_SINGLE_FILE_SIZE}): {name}"
        if "." in name and not name.endswith("/"):
            ext = "." + name.rsplit(".", 1)[-1].lower()
            if ext not in _ALLOWED_EXTENSIONS:
                return f"不允许的文件类型 {ext}: {name}"
        return None

    @staticmethod
    def max_total_size() -> int:
        return _MAX_TOTAL_SIZE

    @staticmethod
    def max_file_count() -> int:
        return _MAX_FILE_COUNT


security_service = SecurityService()