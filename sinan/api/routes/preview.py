# sinan/api/routes/preview.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, desc
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import PageVersion

"""
从 PageVersion 表查询该 marker 下 version 最大的记录，把 html_content 直接以 text/html 返回，浏览器打开就能渲染。

注意点：

order_by(desc(PageVersion.version)).limit(1) 而不是 order_by(desc(PageVersion.id))，
因为 version 才是业务版本号，语义更准确。
不存在时返回 404 JSON，而不是抛异常，这样 curl 测试时信息更清晰。
response_class=HTMLResponse 告诉 FastAPI 和 OpenAPI 文档这个接口返回 HTML，不是 JSON。
"""


router = APIRouter()


@router.get("/page/{marker}", response_class=HTMLResponse)
async def preview_page(marker: str):
    """
    返回指定 marker 的最新版本 HTML 页面。
    直接在浏览器渲染，media_type 为 text/html。
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PageVersion)
            .where(PageVersion.marker == marker)
            .order_by(desc(PageVersion.version))
            .limit(1)
        )
        page = result.scalar_one_or_none()

    if page is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"页面 '{marker}' 不存在"}
        )

    return HTMLResponse(content=page.html_content)