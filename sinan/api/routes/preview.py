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

# sinan/api/routes/preview.py — 在现有代码基础上追加这两个端点

@router.get("/page/{marker}/versions")
async def list_versions(marker: str):
    """列出 marker 下的所有版本（不含 html_content）。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PageVersion)
            .where(PageVersion.marker == marker)
            .order_by(desc(PageVersion.version))
        )
        versions = result.scalars().all()

    if not versions:
        return JSONResponse(status_code=404, content={"detail": f"页面 '{marker}' 不存在"})

    return {
        "marker": marker,
        "versions": [
            {
                "version": v.version,
                "status": v.status,
                "created_at": v.created_at.isoformat(),
            }
            for v in versions
        ],
    }


@router.get("/page/{marker}/version/{version_num}")
async def get_page_version(marker: str, version_num: int):
    """返回指定版本的完整信息（含 html_content）。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PageVersion)
            .where(PageVersion.marker == marker, PageVersion.version == version_num)
        )
        page = result.scalar_one_or_none()

    if page is None:
        return JSONResponse(status_code=404, content={"detail": f"版本 {version_num} 不存在"})

    return {
        "marker": page.marker,
        "version": page.version,
        "status": page.status,
        "html_content": page.html_content,
        "created_at": page.created_at.isoformat(),
    }


# ============================================================
# 参考项目兼容路由：/api/page/preview/...
# 参考位置 page/api/routes/preview.py:41-61
# 参考实现依赖 PreviewService + BOS（Step 9/10），Step 1 先用 PageVersion 表做兼容映射
# ============================================================
page_router = APIRouter(prefix="/api/page", tags=["preview"])


@page_router.get("/preview/{marker}", response_class=HTMLResponse)
async def preview_latest_compat(marker: str):
    """参考兼容：返回 marker 最新版本 HTML。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PageVersion)
            .where(PageVersion.marker == marker)
            .order_by(desc(PageVersion.version))
            .limit(1)
        )
        page = result.scalar_one_or_none()

    if page is None:
        return HTMLResponse(
            content=f"<html><body><h2>页面未找到</h2><p>'{marker}' 尚未生成。</p></body></html>",
            status_code=404,
        )
    return HTMLResponse(content=page.html_content or "")


@page_router.get("/preview/{marker}/v{version}", response_class=HTMLResponse)
async def preview_version_compat(marker: str, version: int):
    """参考兼容：返回 marker 指定版本 HTML（路径形如 /preview/foo/v2）。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PageVersion)
            .where(PageVersion.marker == marker, PageVersion.version == version)
        )
        page = result.scalar_one_or_none()

    if page is None:
        return HTMLResponse(
            content=f"<html><body><h2>版本未找到</h2><p>{marker} v{version} 不存在。</p></body></html>",
            status_code=404,
        )
    return HTMLResponse(content=page.html_content or "")