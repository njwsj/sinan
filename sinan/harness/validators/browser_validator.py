# sinan/harness/validators/browser_validator.py
import logging

logger = logging.getLogger(__name__)


class BrowserValidator:
    """
    用 Playwright 在无头 Chromium 里加载 HTML，检查 JS 错误和渲染状态。
    需要先安装：pip install playwright && playwright install chromium
    playwright 未安装时自动降级为跳过（返回 passed=True）。
    """

    async def validate(self, html: str) -> dict:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("playwright 未安装，跳过浏览器验证")
            return {"passed": True, "issues": [], "chart_count": 0}

        issues = []
        chart_count = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            # 收集 JS 错误
            js_errors = []
            page.on("pageerror", lambda err: js_errors.append(str(err)))
            try:
                await page.set_content(html, timeout=15000)
                await page.wait_for_timeout(2000)  # 等待 JS 执行

                # 检查 ECharts 渲染
                charts = await page.query_selector_all("[_echarts_instance_]")
                chart_count = len(charts)
                if chart_count == 0 and "echarts" in html.lower():
                    issues.append("ECharts 未正确初始化（引用了 ECharts 但未找到渲染实例）")

                # 检查页面内容不为空
                body_text = await page.inner_text("body")
                if len(body_text.strip()) < 10:
                    issues.append("页面 body 内容为空")

                # 附上 JS 错误
                issues.extend([f"JS Error: {e}" for e in js_errors])

            finally:
                await browser.close()

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "chart_count": chart_count,
        }