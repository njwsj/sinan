# sinan/services/page_store.py
import logging
from sqlalchemy import select, desc
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import PageVersion
from sinan.models.enums import PageStatus

logger = logging.getLogger(__name__)


class PageStore:
    """页面版本管理：存储、查询、列举 HTML 版本。
    这个服务负责把生成的 HTML 存进数据库的 page_version 表，并提供版本查询、版本列表等接口。
    """

    async def save(self, marker: str, version: int, html: str, created_by: str = "system") -> PageVersion:
        """保存一个新版本，返回 ORM 对象。"""
        async with AsyncSessionLocal() as db:
            page = PageVersion(
                marker=marker,
                version=version,
                html_content=html,
                status=PageStatus.DRAFT,
                owner=created_by,
                created_by=created_by,
            )
            db.add(page)
            await db.commit()
            await db.refresh(page)
            logger.info("page saved: marker=%s version=%d", marker, version)
            return page

    async def get(self, marker: str, version: int | None = None) -> PageVersion | None:
        """获取指定版本（不传 version 则返回最新版本）。"""
        async with AsyncSessionLocal() as db:
            if version is not None:
                stmt = select(PageVersion).where(
                    PageVersion.marker == marker,
                    PageVersion.version == version,
                )
            else:
                stmt = (
                    select(PageVersion)
                    .where(PageVersion.marker == marker)
                    .order_by(desc(PageVersion.version))
                    .limit(1)
                )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def list_versions(self, marker: str) -> list[PageVersion]:
        """列出某个 marker 下的所有版本，按版本号倒序。"""
        async with AsyncSessionLocal() as db:
            stmt = (
                select(PageVersion)
                .where(PageVersion.marker == marker)
                .order_by(desc(PageVersion.version))
            )
            result = await db.execute(stmt)
            return result.scalars().all()

    async def next_version(self, marker: str) -> int:
        """计算下一个版本号（从 1 开始递增）。"""
        versions = await self.list_versions(marker)
        if not versions:
            return 1
        return versions[0].version + 1


page_store = PageStore()