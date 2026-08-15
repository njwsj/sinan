# sinan/agents/fixer.py
import logging
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个前端代码修复专家。
你会收到一段有问题的 HTML 页面代码，以及具体的错误描述。
请修复这些问题，返回完整的、可直接在浏览器运行的 HTML 页面。

要求：
1. 只修复错误描述中提到的问题，不要大改其他内容
2. 返回完整的 HTML 文档（包含 <!DOCTYPE html>、<head>、<body>）
3. 只返回纯 HTML 代码，不要任何 markdown 格式（不要 ```html 包裹）
4. 不要任何解释文字，直接输出修复后的 HTML"""


class FixerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        iteration = state.get("iteration", 0) + 1
        logger.info("fixer running, iteration=%d", iteration)

        user_content = (
            f"错误描述：\n{state.get('verify_message', '未知错误')}\n\n"
            f"需要修复的 HTML：\n{state.get('html', '')}"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        fixed_html = await self.llm.chat(messages, temperature=0.2)
        fixed_html = self._strip_markdown(fixed_html)

        return {
            "html": fixed_html,
            "iteration": iteration,
            # 重置验证状态，让 verify 节点重新校验修复后的 HTML
            "verified": False,
            "verify_message": "",
        }

    def _strip_markdown(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```html"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()