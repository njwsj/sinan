# sinan/api/routes/generate.py
import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, Query
from sse_starlette.sse import EventSourceResponse

from sinan.config.settings import settings
from sinan.models import events
from sinan.models.contracts import GenerateRequest
from sinan.services.generation_event_bus import event_bus
from sinan.services.session_store import session_store
from sinan.services.generation_job_store import generation_job_store
from sinan.services.generation_supervisor import ensure_job_running
from sinan.services import cancel_registry
logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/page", tags=["generate"])
legacy_router = APIRouter(prefix="/api/v1", tags=["legacy"], include_in_schema=False)
_TRANSITIONAL_USER_ID = "anonymous"


def _resolve_cursor(last_event_id: str | None, cursor: str | None) -> str | None:
    """Last-Event-ID 头优先于 cursor query，二者都缺则从头回放。"""
    return last_event_id or cursor

async def _stream_generation_events(session_id: str, cursor: str | None = None) -> AsyncIterator[dict]:
    """
    先回放游标之后的历史事件，再实时订阅；遇终止事件关闭本次连接。

    游标的语义是"我已经收到了 cursor 及以前的全部事件"，所以需要补的是 cursor 之后还没收到的那部分。

    终止只结束当前 SSE 流，事件仍留在 Redis 里（带 TTL），
    历史查询和后续重连不受影响。
    整体流程：
        客户端连接（带 cursor="2"）
          → replay：补发 seq=3, seq=4
          → subscribe：等待 seq=5, seq=6 ...
          → 收到 completed → return，SSE 关闭

        客户端中途断线
          → CancelledError → 记日志 → return
          → Redis 里事件还在，下次重连从断点继续

    """
    last_id = cursor
    try:
        """
        补历史（replay）一次性把 cursor 之后的历史事件全部发出去。比如客户端断线前收到了 seq=2，重连后这里把 seq=3、seq=4 补发过去。
        """
        for event in await event_bus.replay(session_id, last_id):
            last_id = event.event_id
            yield event.to_sse()
            if event.is_terminal:
                return

        """
        实时订阅（subscribe）从 last_id 开始持续轮询新事件。Runner 每发一条新事件，这里就 yield 给客户端。
        收到终止事件（completed/error/cancelled）后 return，关闭本次 SSE 连接。
        """
        async for event in event_bus.subscribe(session_id, last_id):
            last_id = event.event_id
            yield event.to_sse()
            if event.is_terminal:
                return
    except asyncio.CancelledError:
        logger.info("generation SSE subscriber disconnected: session_id=%s", session_id)
        return


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
    await session_store.create_or_get(
        session_id=session_id,
        user_id=_TRANSITIONAL_USER_ID,
        prompt=req.prompt,
        marker=marker,
    )

    payload = req.model_dump(mode="json")
    result = await generation_job_store.create_or_get_job(
        session_id=session_id, marker=marker, user_id=_TRANSITIONAL_USER_ID,
        payload=payload, reconnect=bool(req.session_id),
    )

    if result.created:
        event_id = await event_bus.publish(
            session_id,
            events.SESSION_INIT,
            events.session_init_data(session_id, marker, cursor=""),
            job_id=result.job.job_id,
            marker=marker,
        )
        logger.info("session initialized: session_id=%s cursor=%s", session_id, event_id)
        ensure_job_running(result.job.job_id)

    return session_id, marker, result.created




@router.post("/generate")
async def create_generation(
    req: GenerateRequest,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    cursor: str | None = Query(default=None),
):
    """参考项目兼容入口：POST 请求本身直接建立 SSE。"""

    session_id, marker, created = await _create_or_reuse_generation(req)
    resume_from = _resolve_cursor(last_event_id, cursor)
    return EventSourceResponse(
        _stream_generation_events(session_id, resume_from),
        ping=settings.sse_ping_seconds,
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
async def stream_generation(
    session_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    cursor: str | None = Query(default=None),
):

    """SSE 长连接：支持 Last-Event-ID / cursor 断线续传。"""

    return EventSourceResponse(
        _stream_generation_events(session_id, _resolve_cursor(last_event_id, cursor)),
        ping=settings.sse_ping_seconds,
    )

@router.post("/generate/{session_id}/cancel")
async def cancel_generation(session_id: str):
    await cancel_registry.cancel_async(session_id)                    # Redis 取消信号 → 运行中 worker 节点边界感知
    await generation_job_store.request_cancel(session_id=session_id)  # pending / 其它实例的 Job 直接置 cancelled
    return {"session_id": session_id, "status": "cancelling"}