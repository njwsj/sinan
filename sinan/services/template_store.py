# sinan/services/template_store.py
"""PageTemplate 的读写服务。
对齐参考 page/api/routes/template.py 和 page/api/routes/prompt_template.py，
把数据库操作集中在这里，路由只做 HTTP 参数解析和响应格式化。
"""
from __future__ import annotations

import uuid
import logging

from sqlalchemy import select, update

from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import PageTemplate
from sinan.services.storage import storage

logger = logging.getLogger(__name__)


class TemplateStore:

    async def list_html_templates(self) -> list[dict]:
        """列出所有 active 的 HTML 模板（type='html'）。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PageTemplate)
                .where(PageTemplate.status == "active", PageTemplate.type == "html")
                .order_by(PageTemplate.id.desc())
            )
            rows = result.scalars().all()
        return [
            {
                "template_id": row.template_id,
                "name": row.name,
                "description": row.description,
                "category": row.category,
                "sub_category": row.sub_category,
                "thumbnail_url": (
                    await storage.signed_url(row.thumbnail_path)
                    if row.thumbnail_path else ""
                ),
                "preview_url": await storage.signed_url(
                    f"template/{row.template_id}/index.html"
                ),
            }
            for row in rows
        ]

    async def list_prompt_templates(self) -> list[dict]:
        """列出所有 active 的 Prompt 模板（type='prompt'）。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PageTemplate)
                .where(PageTemplate.status == "active", PageTemplate.type == "prompt")
                .order_by(PageTemplate.id.desc())
            )
            rows = result.scalars().all()
        return [
            {
                "template_id": row.template_id,
                "name": row.name,
                "description": row.description,
                "category": row.category,
                "sub_category": row.sub_category,
                "thumbnail_url": (
                    await storage.signed_url(row.thumbnail_path)
                    if row.thumbnail_path else ""
                ),
            }
            for row in rows
        ]

    async def get_template(self, template_id: str, type_: str | None = None) -> PageTemplate | None:
        """按 template_id 查询，可选按 type 过滤。"""
        async with AsyncSessionLocal() as db:
            stmt = select(PageTemplate).where(PageTemplate.template_id == template_id)
            if type_:
                stmt = stmt.where(PageTemplate.type == type_)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    async def create_html_template(
        self,
        *,
        name: str,
        description: str = "",
        category: str = "",
        sub_category: str = "",
        html_content: bytes,
        thumbnail_content: bytes,
        thumbnail_content_type: str = "image/png",
        created_by: str = "",
    ) -> PageTemplate:
        """上传一个新的 HTML 模板（含缩略图），落库，返回 ORM 对象。"""
        template_id = uuid.uuid4().hex

        # 上传 HTML 文件
        html_key = f"template/{template_id}/index.html"
        await storage.put(html_key, html_content, "text/html")

        # 上传缩略图
        thumb_key = f"template/{template_id}/thumbnail"
        await storage.put(thumb_key, thumbnail_content, thumbnail_content_type)

        async with AsyncSessionLocal() as db:
            row = PageTemplate(
                template_id=template_id,
                name=name,
                description=description,
                category=category,
                sub_category=sub_category,
                bos_path=html_key,
                thumbnail_path=thumb_key,
                type="html",
                status="active",
                created_by=created_by,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return row

    async def offline_template(self, template_id: str) -> bool:
        """下线模板（status → 'offline'）。返回 True 表示找到并更新了。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PageTemplate).where(PageTemplate.template_id == template_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            await db.execute(
                update(PageTemplate)
                .where(PageTemplate.template_id == template_id)
                .values(status="offline")
            )
            await db.commit()
        return True

    async def resolve_prompt_template(self, prompt_template_id: str) -> PageTemplate | None:
        """查找有效的 prompt 模板（active + type=prompt）。供 generate 路由调用。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PageTemplate).where(
                    PageTemplate.template_id == prompt_template_id,
                    PageTemplate.type == "prompt",
                    PageTemplate.status == "active",
                )
            )
            return result.scalar_one_or_none()

    async def download_html_template(self, template_id: str) -> str | None:
        """下载 HTML 模板文件内容，返回字符串。模板不存在或读取失败返回 None。"""
        row = await self.get_template(template_id, type_="html")
        if not row or not row.bos_path:
            return None
        try:
            key = row.bos_path.removeprefix("local://")
            data = await storage.get(key)
            return data.decode("utf-8", errors="replace")
        except FileNotFoundError:
            logger.warning("template file not found: template_id=%s key=%s", template_id, row.bos_path)
            return None
        except Exception:
            logger.exception("failed to download template: template_id=%s", template_id)
            return None


template_store = TemplateStore()