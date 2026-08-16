# sinan/api/routes/generate.py
import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from sinan.models.contracts import GenerateRequest
from sinan.services.generation_event_bus import event_bus
from sinan.services.generation_runner import generation_runner
from sinan.services.session_store import session_store

"""
POST /api/v1/generate：
接收 GenerateRequest（prompt、user_id、attachments），调用 session_store 创建数据库记录，
然后用 asyncio.create_task 把生成任务扔到后台异步执行，立即返回 session_id。

attachments 格式（来自 /api/v1/data/upload 的响应）：
  [{"file_id": "abc123", "filename": "sales.xlsx", "columns": [...], "row_count": 100}]
Runner 会从本地文件加载完整数据，在进入 LangGraph 之前拼进 prompt。

GET /api/v1/generate/{session_id}/stream：
SSE 长连接，订阅 event_bus 里这个 session 的事件队列，
把每一条事件推送给客户端。客户端可以在任意时刻连接，asyncio.Queue 会缓存 runner 已经发出但还没被消费的事件。
"""

router = APIRouter(prefix="/api/page", tags=["generate"])
legacy_router = APIRouter(prefix="/api/v1", tags=["legacy"], include_in_schema=False)
_TRANSITIONAL_USER_ID = "anonymous"

async def _stream_generation_events(session_id: str) -> AsyncIterator[dict]:
    async for evt in event_bus.subscribe(session_id):
        yield {
            "event": evt.type,
            "data": json.dumps(evt.data, ensure_ascii=True),
        }


async def _create_or_reuse_generation(
    req: GenerateRequest,
) -> tuple[str, str, bool]:
    session_id = req.session_id or uuid.uuid4().hex
    marker = req.marker or uuid.uuid4().hex

    """
    存在的意义：保证同一个 session_id 只启动一次生成任务。

    第一次 POST：created=True → 建会话 + 起后台生成。
    后续用相同 session_id 再 POST（比如客户端断线后重连）：
    created=False → 不重复起任务，只是重新订阅这个 session 的 SSE 事件流。
    """
    _, created = await session_store.create_or_get(
        session_id=session_id,
        user_id=_TRANSITIONAL_USER_ID,
        prompt=req.prompt,
        marker=marker,
    )

    if created:
        asyncio.create_task(
            generation_runner.start(
                session_id,
                req.attachments,
                marker=marker,
            )
        )

    return session_id, marker, created




@router.post("/generate")
async def create_generation(req: GenerateRequest):
    """参考项目兼容入口：POST 请求本身直接建立 SSE。"""

    session_id, _, _ = await _create_or_reuse_generation(req)
    return EventSourceResponse(
        _stream_generation_events(session_id),
        ping=30,
    )

@legacy_router.post("/generate")
async def create_generation_legacy(req: GenerateRequest):
    """旧 JSON 接口，过渡期保留。"""

    session_id, _, created = await _create_or_reuse_generation(req)
    return {
        "session_id": session_id,
        "status": "running" if created else "existing",
    }

@router.get("/generate/{session_id}/stream")
async def stream_generation(session_id: str):
    """
    SSE 长连接，推送该 session 的生成步骤事件。
    事件格式：event: <step_name>  data: {"message": "..."}
    """
    async def event_generator():
        async for evt in event_bus.subscribe(session_id):
            yield {"event": evt.type, "data": json.dumps(evt.data, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
