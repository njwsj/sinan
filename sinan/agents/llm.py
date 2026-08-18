# sinan/agents/llm.py
import asyncio
import json
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)


def _is_rate_limited(exc: Exception) -> bool:
    """只对 429 限流重试，超时和其他错误直接失败。"""
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code == 429
    )


class LLMClient:
    """
    封装对智谱 /chat/completions 接口的异步调用。
    只对 429 限流重试（指数退避 5s→10s→20s→40s→60s），
    超时（ReadTimeout）和其他错误直接失败，不浪费等待时间。
    """

    def __init__(self, api_key: str, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @retry(
        retry=retry_if_exception(_is_rate_limited),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """
        发送 messages 给 LLM，返回纯文本回复内容。

        :param messages: OpenAI 格式的对话列表
        :param temperature: 生成温度，0.3 适合代码/HTML 生成，0.7 适合创意内容
        :raises httpx.HTTPStatusError: HTTP 429 时触发 tenacity 重试（指数退避）
        :raises httpx.ReadTimeout: 响应超时，直接失败不重试
        """
        async with httpx.AsyncClient(timeout=300) as client:
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
            if not resp.is_success:
                logger.error("LLM error: status=%d body=%s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def astream(self, messages: list[dict], temperature: float = 0.7):
        """
        流式调用 LLM，逐 token yield 文本片段。
        用于 coder/analyzer/designer 节点实时推送生成进度。
        429 限流时等待后重试（最多 5 次，指数退避 5s→10s→20s→40s→60s）。
        """
        for attempt in range(5):
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": temperature,
                            "stream": True,
                        },
                    ) as resp:
                        if resp.status_code == 429:
                            wait = min(5 * (2 ** attempt), 60)
                            logger.warning("LLM stream 429, retry %d/%d after %ds", attempt + 1, 5, wait)
                            await asyncio.sleep(wait)
                            continue
                        if not resp.is_success:
                            body = await resp.aread()
                            logger.error("LLM stream error: status=%d body=%s", resp.status_code, body)
                            resp.raise_for_status()
                        buffer = ""
                        async for chunk_text in resp.aiter_text():
                            buffer += chunk_text
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                line = line.rstrip("\r")
                                if not line or not line.startswith("data: "):
                                    continue
                                data = line[6:]
                                if data.strip() == "[DONE]":
                                    return
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk["choices"][0]["delta"].get("content", "")
                                    if delta:
                                        yield delta
                                except (json.JSONDecodeError, KeyError, IndexError):
                                    continue
                        return  # 正常完成
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < 4:
                    wait = min(5 * (2 ** attempt), 60)
                    logger.warning("LLM stream 429 (exc), retry %d/%d after %ds", attempt + 1, 5, wait)
                    await asyncio.sleep(wait)
                    continue
                raise
        raise RuntimeError("LLM stream 429 限流，已重试 5 次仍失败")
