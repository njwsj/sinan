# sinan/api/routes/generate.py
import asyncio
import json
from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus
from sinan.services.generation_runner import generation_runner

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

router = APIRouter()


class GenerateRequest(BaseModel):
    """生成接口入参模型。"""
    prompt: str
    user_id: str = "anonymous"
    attachments: list[dict] = []  # 可选：来自 /data/upload 的附件元数据列表


@router.post("/generate")
async def create_generation(req: GenerateRequest):
    """
    创建生成任务。
    立即返回 session_id，后台异步执行生成流程。
    """
    session = await session_store.create(user_id=req.user_id, prompt=req.prompt)
    asyncio.create_task(generation_runner.start(session.session_id, req.attachments))
    return {"session_id": session.session_id, "status": "running"}


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
