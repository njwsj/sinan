# sinan/harness/validators/render.py
"""渲染校验：Playwright 加载页面，采集 JS 运行时错误。

对齐参考 page/harness/validators/render.py 的 JS 错误采集部分（pageerror +
console.error 双通道 + 去重 + 分类）。

明确差异（记入兼容矩阵）：参考还会截全图交给 Vision LLM 做 28 项视觉检查
（图表空白、legend 重叠等），sinan 本 Step 不接 Vision，因此参考可能产出的
render_visual_* 类 issue 在 sinan 侧不会出现，修复轮数与最终质量分可能偏高。
Vision 检查待 Step 13/15 补齐。

settings.render_validation_enabled 默认 False：没装 playwright 时整体跳过。
"""
from __future__ import annotations

import logging
import os
import tempfile

from sinan.config.settings import settings
from sinan.models.contracts import ValidationIssue
from sinan.models.enums import IssueSeverity

logger = logging.getLogger(__name__)

_JS_ERROR_KEYWORDS = (
    "SyntaxError", "ReferenceError", "TypeError", "RangeError", "URIError", "EvalError",
)


def _dedup_js_errors(errors: list[str]) -> list[str]:
    """pageerror 和 console.error 可能对同一错误各报一次，去重时剥掉前缀再比。"""
    seen: list[str] = []
    for err in errors:
        normalised = err.removeprefix("[console.error] ")
        if not any(normalised == e.removeprefix("[console.error] ") for e in seen):
            seen.append(err)
    return seen


class RenderValidator:
    """渲染期 JS 错误校验。"""

    async def validate(self, code: str) -> list[ValidationIssue]:
        if not settings.render_validation_enabled:
            return []
        if not code or len(code.strip()) < 100:
            return []
        try:
            js_errors = await self._collect_js_errors(code)
        except Exception:
            logger.exception("RenderValidator: 渲染失败，跳过渲染校验")
            return []
        return self._js_errors_to_issues(_dedup_js_errors(js_errors))

    @staticmethod
    async def _collect_js_errors(code: str) -> list[str]:
        from playwright.async_api import async_playwright

        with tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False) as f:
            f.write(code)
            tmp_path = f.name

        js_errors: list[str] = []
        try:
            async with async_playwright() as p:
                launch_kwargs: dict = {
                    "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                }
                chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
                if chromium_path:
                    launch_kwargs["executable_path"] = chromium_path
                browser = await p.chromium.launch(**launch_kwargs)
                page = await browser.new_page(viewport={"width": 1440, "height": 900})
                page.on("pageerror", lambda err: js_errors.append(str(err)))

                def _on_console(msg: object) -> None:
                    # Chrome 有时把内联脚本的 SyntaxError 只发到 console 而不发 pageerror，
                    # 所以两个通道都要收；用关键词过滤掉资源加载失败等噪音。
                    try:
                        if getattr(msg, "type", "") == "error":
                            text = str(getattr(msg, "text", "") or "")
                            if text and any(kw in text for kw in _JS_ERROR_KEYWORDS):
                                js_errors.append(f"[console.error] {text}")
                    except Exception:
                        pass

                page.on("console", _on_console)
                await page.goto(f"file://{tmp_path}")
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(1500)
                await browser.close()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return js_errors

    @staticmethod
    def _js_errors_to_issues(js_errors: list[str]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for i, err in enumerate(js_errors[:5]):   # 上限 5 条，避免噪音淹没修复 prompt
            low = err.lower()
            if "syntaxerror" in low:
                text = "JS SyntaxError 导致页面脚本无法执行"
                suggestion = "检查字符串拼接生成 HTML 的引号闭合，建议改用 template literal"
            elif "referenceerror" in low:
                text = "JS ReferenceError：引用了未声明的变量"
                suggestion = "检查变量名大小写是否与声明一致"
            elif "typeerror" in low:
                text = "JS TypeError：对 null/undefined 进行了非法操作"
                suggestion = "对可能为 null/undefined 的值做防御性判断（?.、|| 默认值）"
            else:
                text = "JS 运行时错误导致页面异常"
                suggestion = "修复页面 JS 运行时错误，确保脚本正常执行"
            issues.append(ValidationIssue(
                issue_id=f"render_js_error_{i}",
                severity=IssueSeverity.P0.value,
                category="render",
                description=f"{text}：{err[:120]}",
                suggestion=suggestion,
            ))
        return issues