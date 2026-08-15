# sinan/agents/verifier.py
from sinan.agents.state import PageGenState
from sinan.harness.validators.browser_validator import BrowserValidator


class VerifierAgent:
    """
    轻量级 HTML 结构校验，不调用 LLM。
    只做必要性检查：有 DOCTYPE、有 html 标签、有 body 标签、长度达标。
    """

    MIN_HTML_LENGTH = 200

    async def run(self, state: PageGenState) -> dict:
        html = state.get("html", "")
        errors = []

        if "<!DOCTYPE HTML>" not in html.upper()[:200]:
            errors.append("缺少 <!DOCTYPE html>")
        if "<html" not in html.lower():
            errors.append("缺少 <html> 标签")
        if "<body" not in html.lower():
            errors.append("缺少 <body> 标签")
        if len(html) < self.MIN_HTML_LENGTH:
            errors.append(f"HTML 内容过短（{len(html)} 字符），疑似生成失败")

        browser_result = await BrowserValidator().validate(html)
        if not browser_result["passed"]:
            errors.extend(browser_result["issues"])

        if errors:
            return {"verified": False, "verify_message": "；".join(errors)}
        return {"verified": True, "verify_message": "校验通过"}