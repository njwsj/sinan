# sinan/api/routes/template.py
"""HTML 模板管理路由。
对齐参考 page/api/routes/template.py：
  POST   /api/page/templates          - 上传模板
  PATCH  /api/page/templates/{template_id}/offline - 下线模板
  GET    /api/page/templates          - 列出模板
"""
import logging

from fastapi import APIRouter, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse

from sinan.services.template_store import template_store

router = APIRouter(prefix="/api/page/templates", tags=["template"])
logger = logging.getLogger(__name__)


@router.post("")
async def upload_template(
    file: UploadFile = File(...),
    thumbnail: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(default=""),
    category: str = Form(default=""),
    sub_category: str = Form(default=""),
    x_user: str | None = Header(default=None, alias="X-User"),
):
    """上传新的 HTML 模板，包含模板文件和缩略图。"""
    html_content = await file.read()
    if not html_content:
        return JSONResponse(status_code=400, content={"code": 400, "message": "模板文件不能为空"})

    thumbnail_content = await thumbnail.read()
    if not thumbnail_content:
        return JSONResponse(status_code=400, content={"code": 400, "message": "缩略图不能为空"})

    try:
        row = await template_store.create_html_template(
            name=name,
            description=description,
            category=category,
            sub_category=sub_category,
            html_content=html_content,
            thumbnail_content=thumbnail_content,
            thumbnail_content_type=thumbnail.content_type or "image/png",
            created_by=x_user or "",
        )
    except Exception as e:
        logger.exception("template upload failed")
        return JSONResponse(status_code=500, content={"code": 500, "message": f"模板上传失败: {e}"})

    from sinan.services.storage import storage
    return {
        "code": 0,
        "data": {
            "template_id": row.template_id,
            "name": row.name,
            "description": row.description,
            "category": row.category,
            "sub_category": row.sub_category,
            "thumbnail_url": await storage.signed_url(row.thumbnail_path) if row.thumbnail_path else "",
        },
    }


@router.patch("/{template_id}/offline")
async def offline_template(template_id: str):
    """下线指定模板（status → offline）。"""
    found = await template_store.offline_template(template_id)
    if not found:
        return JSONResponse(status_code=404, content={"code": 404, "message": "模板不存在"})
    return {"code": 0, "data": {"template_id": template_id, "status": "offline"}}


@router.get("")
async def list_templates():
    """列出所有 active 的 HTML 模板。"""
    templates = await template_store.list_html_templates()
    return {"code": 0, "data": templates}