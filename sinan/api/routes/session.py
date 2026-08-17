# sinan/api/routes/session.py
"""Session 资源路由（Step 1 桩实现，数据字段待 Step 4 填充）。

参考位置 page/api/routes/session.py:331
认证：Step 1 暂不校验，待 Step 3 加 Depends(login_required)。
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from sinan.services.session_store import session_store

router = APIRouter(prefix="/api/page", tags=["session"])


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """返回会话概要（桩：完整 Job/事件视图待 Step 4）。"""
    session = await session_store.get(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"detail": f"session '{session_id}' 不存在"})

    return {
        "session_id": session.session_id,
        "status": session.status.value if session.status else None,
        "marker": session.marker,
        "version": session.version,
        "preview_url": session.preview_url,
        "_stub": "pending Step 4",
    }