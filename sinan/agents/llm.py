# sinan/agents/llm.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class LLMClient:
    """
    封装对智谱 /chat/completions 接口的异步调用。
    带 tenacity 自动重试：失败后最多重试 3 次，等待时间指数增长（1s → 10s）。
    """

    def __init__(self, api_key: str, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """
        发送 messages 给 LLM，返回纯文本回复内容。

        :param messages: OpenAI 格式的对话列表，例如
                         [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        :param temperature: 生成温度，0.3 适合代码/HTML 生成，0.7 适合创意内容
        :raises httpx.HTTPStatusError: HTTP 4xx/5xx 时抛出，触发 tenacity 重试
        """
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
