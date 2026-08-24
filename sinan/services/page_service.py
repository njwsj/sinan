# sinan/services/page_service.py
"""页面生命周期服务（Step 10 新增）。

职责：在 page_store 原子操作基础上增加业务校验。
  - publish_page    : 校验版本存在后发布，写 published_version + status=published
  - unpublish_page  : 状态回退到 preview，清 published_version
  - rollback_version: 只移动 current_version 指针，不删历史版本
  - get_page / list_versions: 包装 page_store，返回 API 友好的 dict

对齐参考 page/api/routes/hosting.py 的发布链路；参考无独立 page_service，
sinan 将其单独提取以便后续测试。
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from sinan.models.database import AsyncSessionLocal
from sinan.models.enums import PageStatus
from sinan.models.tables import Page
from sinan.services.page_store import page_store

logger = logging.getLogger(__name__)


class PageService:

    # ------------------------------------------------------------------ #
    # 查询                                                                  #
    # ------------------------------------------------------------------ #

    async def get_page(self, marker: str) -> dict | None:
        """获取页面主表摘要。"""
        page = await page_store.get_page(marker)
        if page is None:
            return None
        return {
            "marker": page.marker,
            "title": page.title,
            "status": page.status,
            "current_version": page.current_version,
            "published_version": page.published_version,
            "published_to": page.published_to,
            "quality_score": page.quality_score,
            "created_at": page.created_at.isoformat() if page.created_at else None,
            "updated_at": page.updated_at.isoformat() if page.updated_at else None,
        }

    async def list_versions(self, marker: str) -> list[dict]:
        """列出版本元数据（不含 html_content）。"""
        versions = await page_store.list_versions(marker)
        return [
            {
                "version": v.version,
                "content_hash": v.content_hash,
                "code_size": v.code_size,
                "harness_score": v.harness_score,
                "repair_rounds": v.repair_rounds,
                "security_scan": v.security_scan,
                "note": v.note,
                "created_by": v.created_by,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]

    # ------------------------------------------------------------------ #
    # 写操作                                                                #
    # ------------------------------------------------------------------ #

    async def publish_page(
        self, marker: str, version: int, published_to: str = ""
    ) -> dict:
        """发布指定版本。版本不存在时返回 ok=False。

        验收：发布只发布指定版本，不影响 current_version。
        """
        pv = await page_store.get(marker, version)
        if pv is None:
            return {"ok": False, "error": f"版本 {version} 不存在"}
        await page_store.publish(marker, version, published_to)
        logger.info("page published: marker=%s version=%d to=%s", marker, version, published_to)
        return {
            "ok": True,
            "marker": marker,
            "version": version,
            "published_to": published_to,
            "preview_url": f"/api/page/preview/{marker}/v{version}",
        }

    async def unpublish_page(self, marker: str) -> dict:
        """取消发布，状态回退到 preview，清 published_version。

        验收：unpublish 不删除任何版本，只改 Page 表指针。
        """
        async with AsyncSessionLocal() as db:
            page = (
                await db.execute(select(Page).where(Page.marker == marker))
            ).scalar_one_or_none()
            if page is None:
                return {"ok": False, "error": "页面不存在"}
            if page.status != PageStatus.PUBLISHED.value:
                return {
                    "ok": False,
                    "error": f"页面当前状态 {page.status!r}，不在发布状态，无需取消",
                }
            page.status = PageStatus.PREVIEW.value
            page.published_version = None
            page.published_to = ""
            await db.commit()
        logger.info("page unpublished: marker=%s", marker)
        return {"ok": True, "marker": marker, "status": PageStatus.PREVIEW.value}

    async def rollback_version(self, marker: str, version: int) -> dict:
        """回滚到指定版本（只移动 current_version 指针，不删除历史版本）。

        验收：回滚只改变 current/published 指针，历史版本全部保留。
        """
        pv = await page_store.get(marker, version)
        if pv is None:
            return {"ok": False, "error": f"版本 {version} 不存在，无法回滚"}
        async with AsyncSessionLocal() as db:
            page = (
                await db.execute(select(Page).where(Page.marker == marker))
            ).scalar_one_or_none()
            if page is None:
                return {"ok": False, "error": "页面不存在"}
            old_version = page.current_version
            page.current_version = version
            await db.commit()
        logger.info(
            "page rolled back: marker=%s %d→%d", marker, old_version, version
        )
        return {
            "ok": True,
            "marker": marker,
            "current_version": version,
            "preview_url": f"/api/page/preview/{marker}/v{version}",
        }


page_service = PageService()