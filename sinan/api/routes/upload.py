# sinan/api/routes/upload.py
"""文件上传路由，Step 9 起对齐参考 page/api/routes/upload.py。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from sinan.services.data_service import data_service
from sinan.services.session_store import session_store

router = APIRouter(prefix="/api/page", tags=["upload"])
logger = logging.getLogger(__name__)

_ALLOWED_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".pdf", ".txt", ".md", ".markdown",
    ".csv", ".json", ".xml", ".yaml", ".yml",
    ".html", ".htm", ".xlsx", ".xls",
    ".doc", ".docx", ".ppt", ".pptx", ".zip",
}
_MAX_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
    marker: str = Form(default=""),
):
    """上传附件，解析后写入 LocalStorage 和 attachment 表。"""
    filename = file.filename or "unnamed"
    ct = file.content_type or ""

    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in _ALLOWED_EXTS:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": f"不支持的文件类型: {ext or filename}"},
        )

    content = await file.read()
    if len(content) > _MAX_SIZE:
        return JSONResponse(status_code=400, content={"code": 400, "message": "文件大小超过 10MB 限制"})

    try:
        meta = await data_service.parse_and_store(
            file_data=content,
            filename=filename,
            content_type=ct,
            session_id=session_id or None,
            marker=marker or None,
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content={"code": 400, "message": str(e)})
    except Exception as e:
        logger.exception("upload 失败: filename=%s", filename)
        return JSONResponse(status_code=500, content={"code": 500, "message": f"内部错误: {e}"})

    attachment_record = {**meta, "size": len(content)}
    try:
        if session_id:
            await session_store.save_attachment(session_id, attachment_record)
        elif marker:
            await session_store.save_attachment_by_marker(marker, attachment_record)
    except Exception:
        logger.exception("写 attachment 表失败，不影响上传结果")

    resp = {
        "file_id": meta["file_id"],
        "filename": filename,
        "size": len(content),
        "content_type": ct,
        "parse_type": meta.get("parse_type", "binary"),
        "sha256": meta.get("sha256", ""),
    }
    if meta.get("parse_type") in ("excel", "csv"):
        resp["columns"] = meta.get("columns", [])
        resp["row_count"] = meta.get("row_count", 0)
        resp["preview"] = meta.get("preview", [])

    return {"code": 0, "data": resp}