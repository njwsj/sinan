# sinan/api/routes/session.py
"""Session 资源路由（Step 1 桩实现，数据字段待 Step 4 填充）。

参考位置 page/api/routes/session.py:331
认证：Step 1 暂不校验，待 Step 3 加 Depends(login_required)。
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from sinan.services.session_store import session_store
from fastapi import APIRouter, Query, Header
from sse_starlette.sse import EventSourceResponse
from sinan.config.settings import settings
from sinan.models.contracts import (
    SessionConfirmRequest, SessionIterateRequest, SessionAbortRequest,
)
from sinan.services.session_action_service import session_action_service
from sinan.api.routes.generate import _stream_generation_events, _resolve_cursor

_TRANSITIONAL_USER_ID = "anonymous"

router = APIRouter(prefix="/api/page", tags=["session"])


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """返回会话概要（桩：完整 Job/事件视图待 Step 4）。"""
    session = await session_store.get(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"detail": f"session '{session_id}' 不存在"})

    return {
        "session_id": session.session_id,
        "status": session.status,
        "pipeline_state": session.pipeline_state,
        "marker": session.marker,
        "version": session.version,
        "preview_url": session.preview_url,
        "_stub": "pending Step 4",
    }

@router.post("/session/{session_id}/confirm")
async def confirm_session(
    session_id: str, req: SessionConfirmRequest,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    cursor: str | None = Query(default=None),
):
    err = await session_action_service.confirm(session_id, _TRANSITIONAL_USER_ID, req)
    if err:                                   # (status_code, detail)
        return JSONResponse(status_code=err[0], content={"detail": err[1]})
    return EventSourceResponse(
        _stream_generation_events(session_id, _resolve_cursor(last_event_id, cursor)),
        ping=settings.sse_ping_seconds,
    )


@router.post("/session/{session_id}/iterate")
async def iterate_session(
    session_id: str, req: SessionIterateRequest,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    cursor: str | None = Query(default=None),
):
    err = await session_action_service.iterate(session_id, _TRANSITIONAL_USER_ID, req)
    if err:
        return JSONResponse(status_code=err[0], content={"detail": err[1]})
    return EventSourceResponse(
        _stream_generation_events(session_id, _resolve_cursor(last_event_id, cursor)),
        ping=settings.sse_ping_seconds,
    )


@router.post("/session/{session_id}/abort")
async def abort_session(session_id: str, req: SessionAbortRequest):
    err = await session_action_service.abort(session_id, _TRANSITIONAL_USER_ID, req)
    if err:
        return JSONResponse(status_code=err[0], content={"detail": err[1]})
    return {"code": 0, "data": {"session_id": session_id, "status": "cancelled"}}