# sinan/api/routes/pages.py
"""Pages 资源路由（Step 1 桩实现，完整字段/权限待 Step 10 填充）。

参考位置 page/api/routes/pages.py:18
认证：Step 1 暂不校验，待 Step 3。
"""
from fastapi import APIRouter
from sqlalchemy import select, desc

from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import PageVersion

router = APIRouter(prefix="/api/page", tags=["pages"])


@router.get("/pages/{marker}/versions")
async def list_page_versions(marker: str):
    """列出 marker 下所有版本（桩：不含内容，仅元数据）。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PageVersion)
            .where(PageVersion.marker == marker)
            .order_by(desc(PageVersion.version))
        )
        versions = result.scalars().all()

    return {
        "marker": marker,
        "versions": [
            {
                "version": v.version,
                "status": v.status.value if v.status else None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
        "_stub": "pending Step 10",
    }