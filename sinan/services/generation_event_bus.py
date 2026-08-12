# sinan/services/generation_event_bus.py
import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator

"""
    提供一个基于内存 asyncio.Queue 的发布/订阅事件通道，用于 runner 和 SSE 路由之间的通信。
    
    架构：内部维护一个 dict[session_id → asyncio.Queue] （self._queues），runner 往 queue 里 put 事件，SSE 路由异步 get 消费。
    publish(session_id, event_type, data)：往对应 queue 推一条事件。
    publish_done(session_id)：推一个哨兵对象 _SENTINEL，通知 subscriber 生成已结束，可以关闭 SSE 连接。
    subscribe(session_id)：异步生成器，不断从 queue 取事件 yield 出去，遇到 _SENTINEL 时停止并清理 queue。
    
    Phase 1注意点：
    _SENTINEL = object() 是一个唯一对象，用 is 判断，不会误判成正常事件。
    如果 SSE 客户端在 runner 开始之前就连上，Queue 会阻塞在 await q.get() 等待，没有竞态问题。
    如果 SSE 客户端断开连接，EventSourceResponse 会取消 event_generator 协程，queue 会留在内存里。
    Phase 1 不处理这个边界情况，Phase 2+ 可以加超时清理。
"""


_SENTINEL = object()  # 用于通知 subscriber 生成流程已结束


@dataclass
class GenerationEvent:
    type: str   # 对应步骤名，如 receive / analyze / design / code / verify / host
    data: dict  # 事件内容，至少包含 {"message": "..."}


class GenerationEventBus:
    def __init__(self):
        # session_id → asyncio.Queue[GenerationEvent | _SENTINEL]
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_or_create_queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    async def publish(self, session_id: str, event_type: str, data: dict) -> None:
        """发布一条步骤事件"""
        q = self._get_or_create_queue(session_id)
        await q.put(GenerationEvent(type=event_type, data=data))

    async def publish_done(self, session_id: str) -> None:
        """通知 subscriber 生成已完成，关闭 SSE 流"""
        q = self._get_or_create_queue(session_id)
        await q.put(_SENTINEL)

    async def subscribe(self, session_id: str) -> AsyncGenerator[GenerationEvent, None]:
        """
        异步生成器：持续 yield 该 session 的事件，直到收到终止信号。
        SSE 路由用 async for 消费。
        """
        q = self._get_or_create_queue(session_id)
        while True:
            item = await q.get()
            if item is _SENTINEL:
                # 清理 queue，防止内存泄漏
                self._queues.pop(session_id, None)
                break
            yield item


# 模块级单例
event_bus = GenerationEventBus()