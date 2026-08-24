# sinan/services/session_store.py
import uuid
from sqlalchemy import select
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSession
from sinan.models.enums import PipelineState, SessionStatus


class SessionStore:
    async def create(
            self,
            user_id: str,
            prompt: str,
            *,
            session_id: str | None = None,
            marker: str | None = None,
            attachments: list | None = None,
    ) -> GenSession:
        """创建新 session，写入数据库，返回 ORM 对象"""
        resolved_session_id = session_id or uuid.uuid4().hex
        session = GenSession(
            session_id=resolved_session_id,
            user_id=user_id,
            prompt=prompt,
            marker=marker,
            title=(prompt or "")[:64],
            attachments=attachments or [],
            status=SessionStatus.ACTIVE.value,
            pipeline_state=PipelineState.INIT.value,
        )
        async with AsyncSessionLocal() as db:
            db.add(session)
            await db.commit()
            await db.refresh(session)
        return session

    async def create_or_get(
        self,
        *,
        session_id: str,
        user_id: str,
        prompt: str,
        marker: str,
        attachments: list | None = None,
    ) -> tuple[GenSession, bool]:
        """返回已有 Session，或者创建新 Session。
        现在的"先查后建"不是并发安全的：如果两个请求几乎同时用同一个 session_id 打进来，
        两边可能都查到 None，于是都去 create + 都 create_task，造成重复建库/重复生成。

        返回值中的 bool 表示是否为本次新建。false 意味着调用者无需再启动生成任务。
        真正并发安全的 Job 去重应在 Step 4 实现。
        """

        existing = await self.get(session_id)
        if existing is not None:
            return existing, False

        session = await self.create(
            user_id=user_id,
            prompt=prompt,
            session_id=session_id,
            marker=marker,
            attachments=attachments,
        )
        return session, True

    async def get(self, session_id: str) -> GenSession | None:
        """按 ID 查询 session，不存在返回 None"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenSession).where(GenSession.session_id == session_id)
            )
            return result.scalar_one_or_none()

    async def update(self, session_id: str, **kwargs) -> None:
        """
        通用字段更新。
        用法示例：await session_store.update(sid, status=SessionStatus.COMPLETED, marker="page_abc")
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenSession).where(GenSession.session_id == session_id)
            )
            session = result.scalar_one_or_none()
            if session is None:
                return
            for key, value in kwargs.items():
                setattr(session, key, value)
            await db.commit()

    async def save_attachment(self, session_id: str, attachment: dict) -> None:
        """把附件元信息写入 attachment 表，session.attachments 只保存 file_id 列表。"""
        from sinan.models.tables import Attachment
        from sqlalchemy import select as _select

        file_id = attachment.get("file_id") or ""
        if not file_id:
            return

        # 1. 写 attachment 表（幂等）
        async with AsyncSessionLocal() as db:
            existing = (
                await db.execute(_select(Attachment).where(Attachment.file_id == file_id))
            ).scalar_one_or_none()
            if existing is None:
                db.add(Attachment(
                    file_id=file_id,
                    session_id=session_id,
                    user_id="",
                    file_name=attachment.get("filename") or "",
                    file_type=attachment.get("parse_type") or "",
                    file_size=attachment.get("size") or 0,
                    storage_path=attachment.get("raw_storage_uri") or attachment.get("storage_uri") or "",
                    row_count=attachment.get("row_count"),
                    meta={k: v for k, v in attachment.items()
                          if k not in ("file_id", "filename", "file_size", "storage_path")},
                ))
                await db.commit()

        # 2. session.attachments 只保存 file_id 字符串列表
        session = await self.get(session_id)
        if session is None:
            return
        current_ids: list[str] = []
        for item in (session.attachments or []):
            fid = item if isinstance(item, str) else item.get("file_id", "")
            if fid:
                current_ids.append(fid)
        if file_id not in current_ids:
            current_ids.append(file_id)
        await self.update(session_id, attachments=current_ids)

    async def save_attachment_by_marker(self, marker: str, attachment: dict) -> None:
        """按 marker 找最近的 session，再调 save_attachment。"""
        from sqlalchemy import select as _select
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                _select(GenSession.session_id)
                .where(GenSession.marker == marker)
                .order_by(GenSession.created_at.desc())
                .limit(1)
            )
            session_id = result.scalar_one_or_none()
        if session_id:
            await self.save_attachment(session_id, attachment)

    async def get_attachment(self, file_id: str):
        """从 attachment 表按 file_id 查询。"""
        from sinan.models.tables import Attachment
        from sqlalchemy import select as _select
        async with AsyncSessionLocal() as db:
            return (
                await db.execute(_select(Attachment).where(Attachment.file_id == file_id))
            ).scalar_one_or_none()


# 模块级单例，路由和 runner 直接 import 使用
session_store = SessionStore()