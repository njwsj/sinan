# sinan/services/session_store.py
import uuid
from sqlalchemy import select
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSession
from sinan.models.enums import SessionStatus


class SessionStore:
    async def create(
            self,
            user_id: str,
            prompt: str,
            *,
            session_id: str | None = None,
            marker: str | None = None,
    ) -> GenSession:
        """创建新 session，写入数据库，返回 ORM 对象"""
        resolved_session_id = session_id or uuid.uuid4().hex
        session = GenSession(
            session_id=resolved_session_id,
            user_id=user_id,
            prompt=prompt,
            marker=marker,
            status=SessionStatus.PENDING,
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


# 模块级单例，路由和 runner 直接 import 使用
session_store = SessionStore()