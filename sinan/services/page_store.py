# sinan/services/page_store.py
import hashlib
import json
import logging

from sqlalchemy import desc, select

from sinan.models.database import AsyncSessionLocal
from sinan.models.enums import PageStatus
from sinan.models.tables import Page, PageVersion

logger = logging.getLogger(__name__)


class PageStore:
    """页面主表 + 版本快照管理。

    Step 6 起 Page 是主表：owner/status/current_version 都在 Page 上；
    PageVersion 只是不可变快照。save() 在一个事务里完成 upsert Page + 插入版本，
    避免出现"有版本没有 Page"或 current_version 落后的中间态。
    """

    async def save(
        self,
        marker: str,
        version: int,
        html: str,
        created_by: str = "system",
        *,
        session_id: str | None = None,
        title: str = "",
        harness_score: float | None = None,
        repair_rounds: int = 0,
        note: str = "",
    ) -> PageVersion:
        """写入一个新版本，并把 Page 主表推进到该版本。"""
        html = html or ""
        content_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

        async with AsyncSessionLocal() as db:
            page = (
                await db.execute(select(Page).where(Page.marker == marker))
            ).scalar_one_or_none()

            if page is None:
                page = Page(
                    marker=marker,
                    session_id=session_id,
                    title=title,
                    owner=created_by,
                    status=PageStatus.PREVIEW.value,
                    current_version=version,
                    quality_score=harness_score,
                )
                db.add(page)
            else:
                page.current_version = max(page.current_version, version)
                if page.status == PageStatus.DRAFT.value:
                    page.status = PageStatus.PREVIEW.value
                if session_id:
                    page.session_id = session_id
                if harness_score is not None:
                    page.quality_score = harness_score

            record = PageVersion(
                marker=marker,
                version=version,
                html_content=html,
                content_hash=content_hash,
                code_size=len(html.encode("utf-8")),
                file_count=1,
                entry_file="index.html",
                file_list=json.dumps(["index.html"]),
                note=note,
                harness_score=harness_score,
                repair_rounds=repair_rounds,
                created_by=created_by,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

        logger.info("page version saved: marker=%s version=%d hash=%s", marker, version, content_hash[:12])
        return record

    async def get_page(self, marker: str) -> Page | None:
        """取 Page 主表记录。"""
        async with AsyncSessionLocal() as db:
            return (
                await db.execute(select(Page).where(Page.marker == marker))
            ).scalar_one_or_none()

    async def get(self, marker: str, version: int | None = None) -> PageVersion | None:
        """获取指定版本快照（不传 version 则返回最新版本）。"""
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
            return (await db.execute(stmt)).scalar_one_or_none()

    async def list_versions(self, marker: str) -> list[PageVersion]:
        """列出某个 marker 下的所有版本，按版本号倒序。"""
        async with AsyncSessionLocal() as db:
            stmt = (
                select(PageVersion)
                .where(PageVersion.marker == marker)
                .order_by(desc(PageVersion.version))
            )
            return list((await db.execute(stmt)).scalars().all())

    async def next_version(self, marker: str) -> int:
        """下一个版本号。以 Page.current_version 为准，Page 不存在时回落到版本表。"""
        async with AsyncSessionLocal() as db:
            current = (
                await db.execute(select(Page.current_version).where(Page.marker == marker))
            ).scalar_one_or_none()
            if current is not None:
                return current + 1
            latest = (
                await db.execute(
                    select(PageVersion.version)
                    .where(PageVersion.marker == marker)
                    .order_by(desc(PageVersion.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            return (latest or 0) + 1

    async def publish(self, marker: str, version: int, published_to: str = "") -> None:
        """把指定版本标记为已发布（完整发布链路见 Step 10）。"""
        async with AsyncSessionLocal() as db:
            page = (
                await db.execute(select(Page).where(Page.marker == marker))
            ).scalar_one_or_none()
            if page is None:
                return
            page.status = PageStatus.PUBLISHED.value
            page.published_version = version
            page.published_to = published_to
            await db.commit()


page_store = PageStore()