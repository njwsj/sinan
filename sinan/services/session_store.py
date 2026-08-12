# sinan/services/session_store.py
import uuid
from sqlalchemy import select
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSession
from sinan.models.enums import SessionStatus


class SessionStore:
    async def create(self, user_id: str, prompt: str) -> GenSession:
        """创建新 session，写入数据库，返回 ORM 对象"""
        session_id = str(uuid.uuid4())
        session = GenSession(
            id=session_id,
            user_id=user_id,
            prompt=prompt,
            status=SessionStatus.PENDING,
        )
        async with AsyncSessionLocal() as db:
            db.add(session)
            await db.commit()
            await db.refresh(session)
        return session

    async def get(self, session_id: str) -> GenSession | None:
        """按 ID 查询 session，不存在返回 None"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenSession).where(GenSession.id == session_id)
            )
            return result.scalar_one_or_none()

    async def update(self, session_id: str, **kwargs) -> None:
        """
        通用字段更新。
        用法示例：await session_store.update(sid, status=SessionStatus.COMPLETED, marker="page_abc")
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenSession).where(GenSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session is None:
                return
            for key, value in kwargs.items():
                setattr(session, key, value)
            await db.commit()


# 模块级单例，路由和 runner 直接 import 使用
session_store = SessionStore()