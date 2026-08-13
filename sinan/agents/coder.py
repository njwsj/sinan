# sinan/agents/coder.py
from sinan.agents.llm import LLMClient


class CoderAgent:
    """
    Phase 2 单步 Coder Agent。
    接收用户描述，直接调 LLM 生成完整 HTML 页面。
    Phase 3 会拆成 Analyzer → Designer → Coder → Verifier 多 Agent 流水线，
    这里先做最简单的单步版本。
    """

    SYSTEM_PROMPT = """你是一个前端页面生成专家。
根据用户的需求描述，生成一个完整的、可直接在浏览器运行的 HTML 页面。

要求：
1. 页面必须是完整的 HTML 文档，包含 <!DOCTYPE html>、<head>、<body>
2. CSS 全部内联在 <style> 标签中，不依赖外部 CSS 文件
3. JavaScript 全部内联在 <script> 标签中
4. 如果需要图表，使用 ECharts（通过 CDN 引入：https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js）
5. 响应式布局，适配不同屏幕宽度
6. 现代化 UI 风格，配色协调，有适当的间距和层次感
7. 只返回纯 HTML 代码，不要任何 markdown 格式（不要 ```html 包裹）
8. 不要任何解释文字，直接输出 HTML"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def generate(self, prompt: str) -> str:
        """
        根据用户描述生成 HTML 页面。

        :param prompt: 用户的自然语言描述，例如 "做一个 GPU 使用率看板"
        :return: 完整的 HTML 字符串
        """
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        html = await self.llm.chat(messages, temperature=0.3)
        return self._strip_markdown(html)

    def _strip_markdown(self, text: str) -> str:
        """
        剥离 LLM 有时会加上的 markdown 代码块包裹。
        处理以下几种常见格式：
          ```html\n...\n```
          ```\n...\n```
        """
        text = text.strip()
        # 处理 ```html 开头
        if text.startswith("```html"):
            text = text[7:]
        # 处理 ``` 开头（没有语言标识）
        elif text.startswith("```"):
            text = text[3:]
        # 处理 ``` 结尾
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()
