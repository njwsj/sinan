# sinan/observability/langfuse.py
"""Langfuse 可观测性封装。

设计要点：
- 懒加载：``langfuse_enabled=False`` 或缺 key 时，所有函数都是 no-op。
- 防御式：任何 Langfuse 初始化/上报异常都被吞掉并记日志，**绝不阻断主流程**。
- trace 用 contextvars 传播：在 generation_runner.run_job 里用 ``with trace(...)``
  打开一条 trace，同一条 asyncio task 内后续所有 ``generation()`` 自动挂到它下面，
  跨模块（节点里的 LLMClient）无需显式传 trace 对象。
"""
from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from sinan.config.settings import settings

logger = logging.getLogger(__name__)

_client = None
_init_failed = False
_current_trace: contextvars.ContextVar = contextvars.ContextVar(
    "langfuse_current_trace", default=None
)


def is_enabled() -> bool:
    return bool(
        settings.langfuse_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    )


def get_client():
    """懒加载 Langfuse 客户端；未启用或初始化失败时返回 None。"""
    global _client, _init_failed
    if _client is None and not _init_failed and is_enabled():
        try:
            from langfuse import Langfuse  # 延迟导入：未装包也能正常启动
            _client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
        except Exception:
            _init_failed = True
            logger.exception("初始化 Langfuse 客户端失败，本次进程内停用 tracing")
    return _client


@contextmanager
def trace(name: str, **kwargs: Any) -> Iterator[Any]:
    """打开一条 Langfuse trace，作为当前上下文里所有 generation 的父级。

    :param name: trace 名称
    :param kwargs: 透传给 ``client.trace``，如 user_id / session_id / input / metadata
    """
    t = None
    token = None
    try:
        client = get_client()
        if client is not None:
            t = client.trace(name=name, **kwargs)
            token = _current_trace.set(t)
    except Exception:
        logger.exception("创建 Langfuse trace 失败")
        t = None
    try:
        yield t
    finally:
        if token is not None:
            _current_trace.reset(token)


def generation(name: str, **kwargs: Any) -> Optional[Any]:
    """在当前 trace 下创建一条 generation；无活动 trace 时降级为独立 trace。

    :param name: generation 名称
    :param kwargs: 透传给 ``trace.generation``，如 model / input / output / usage
    :return: StatefulGenerationClient，未启用/失败时返回 None（调用方需判空）
    """
    try:
        client = get_client()
        if client is None:
            return None
        parent = _current_trace.get()
        if parent is not None:
            return parent.generation(name=name, **kwargs)
        # 没有活动 trace（例如脱离 run_job 直接调 LLM 的路径），退化为单 generation 的 trace
        return client.trace(name=name).generation(name=name, **kwargs)
    except Exception:
        logger.exception("创建 Langfuse generation 失败")
        return None


def usage_from_openai(usage: dict | None) -> dict | None:
    """把 OpenAI/智谱风格的 usage 转成 Langfuse ModelUsage（dict）。

    ``{"prompt_tokens", "completion_tokens", "total_tokens"}``
    → ``{"input", "output", "total"}``
    """
    if not usage:
        return None
    return {
        "input": usage.get("prompt_tokens"),
        "output": usage.get("completion_tokens"),
        "total": usage.get("total_tokens"),
    }


def flush() -> None:
    """同步冲刷待上报事件（服务退出时兜底；SDK 后台线程平时会自动上报）。"""
    try:
        client = get_client()
        if client is not None:
            client.flush()
    except Exception:
        logger.warning("Langfuse flush 失败", exc_info=True)
