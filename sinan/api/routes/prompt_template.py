# sinan/api/routes/prompt_template.py
"""Prompt 模板管理路由。
对齐参考 page/api/routes/prompt_template.py：
  GET /api/page/prompt/templates              - 列出 prompt 模板
  GET /api/page/prompt/templates/{template_id} - 查询单个 prompt 模板
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from sinan.services.template_store import template_store
from sinan.services.storage import storage

router = APIRouter(prefix="/api/page/prompt/templates", tags=["prompt-template"])


@router.get("")
async def list_prompt_templates():
    """列出所有 active 的 Prompt 模板。"""
    templates = await template_store.list_prompt_templates()
    return {"code": 0, "data": templates}


@router.get("/{template_id}")
async def get_prompt_template(template_id: str):
    """查询单个 Prompt 模板。"""
    row = await template_store.get_template(template_id, type_="prompt")
    if not row:
        return JSONResponse(status_code=404, content={"code": 404, "message": "Prompt模板不存在"})
    return {
        "code": 0,
        "data": {
            "template_id": row.template_id,
            "name": row.name,
            "description": row.description,
            "category": row.category,
            "sub_category": row.sub_category,
            "thumbnail_url": (
                await storage.signed_url(row.thumbnail_path)
                if row.thumbnail_path else ""
            ),
        },
    }