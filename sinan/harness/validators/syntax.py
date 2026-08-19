# sinan/harness/validators/syntax.py
"""JS 语法校验：对每个 <script> 块跑 `node --check`。

对齐参考 page/harness/validators/syntax.py。node 不可用时只 warning、返回空列表
（不能报 issue，否则没装 node 的环境会稳定多出 P0，和参考对不上）。
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile

from sinan.models.contracts import ValidationIssue
from sinan.models.enums import IssueSeverity

_NODE_CHECK_TIMEOUT = 5

logger = logging.getLogger(__name__)


class SyntaxValidator:
    """用 node --check 检查内联 JS 的语法错误。"""

    def validate(self, code: str) -> list[ValidationIssue]:
        if not code or len(code.strip()) < 50:
            return []
        blocks = re.findall(r"<script(?:\s[^>]*)?>(\s*[\s\S]*?)</script>", code, re.IGNORECASE)
        if not blocks:
            return []

        node_bin = self._find_node()
        if not node_bin:
            logger.warning("SyntaxValidator: 未找到 node，跳过 JS 语法检查")
            return []

        issues: list[ValidationIssue] = []
        for i, js in enumerate(blocks):
            issues.extend(self._check_block(node_bin, js, i))
        return issues

    @staticmethod
    def _find_node() -> str | None:
        node = os.environ.get("NODE_BIN") or "node"
        try:
            result = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                return node
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @staticmethod
    def _check_block(node_bin: str, js_code: str, block_index: int) -> list[ValidationIssue]:
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", encoding="utf-8", delete=False) as f:
            f.write(js_code)
            tmp_path = f.name
        try:
            result = subprocess.run(
                [node_bin, "--check", tmp_path],
                capture_output=True, text=True, timeout=_NODE_CHECK_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return []
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if result.returncode == 0:
            return []

        stderr = (result.stderr or "").strip()
        error_msg = ""
        error_line = ""
        for line in stderr.splitlines():
            line = line.strip()
            if any(k in line for k in ("SyntaxError:", "ReferenceError:", "TypeError:")):
                error_msg = line
            elif re.match(r"^/.+:\d+$", line) and not error_line:
                error_line = re.sub(r"^/.+:", "line ", line)

        description = f"Script block {block_index + 1} JS 语法错误"
        if error_msg:
            description += f"：{error_msg}"
        if error_line:
            description += f"（{error_line}）"

        if "SyntaxError" in stderr:
            suggestion = (
                "检查 JS 字符串拼接生成 HTML 时是否有未闭合的引号或括号；"
                "建议用 template literal（反引号）代替字符串拼接"
            )
        else:
            suggestion = "修复 JS 语法错误，确保脚本可被 Node.js 解析执行"

        return [ValidationIssue(
            issue_id=f"syntax_js_error_{block_index}",
            severity=IssueSeverity.P0.value,
            category="syntax",
            description=description,
            suggestion=suggestion,
        )]