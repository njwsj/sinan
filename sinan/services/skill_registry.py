# sinan/services/skill_registry.py
"""Skill 注册表：skill_definition 表的读写门面。

对齐参考 page/services/skill_registry.py 的方法集与返回字段，差异只有两处：
  1. install_skill 从本地目录装（见 skill_package），不下载 zip；
  2. 状态多一个 failed（本地包缺 handler.py 时），参考只有 enabled/disabled。

状态取值：enabled / disabled / installing / failed（计划 12.1 要求的四态）。
本地安装是同步的，installing 只在 sync 过程中短暂出现，保留取值以便将来接远端。
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select, update

from sinan.config.settings import settings
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import SkillDefinition
from sinan.services import skill_package

logger = logging.getLogger(__name__)

VALID_STATUS = ("enabled", "disabled", "installing", "failed")


class SkillRegistry:
    """安装在本地的 Skill 的唯一读写入口。"""

    # ---------- 查询 ----------

    async def list_skills(self, status: str | None = None, *,
                          visibility: str | None = None,
                          include_content: bool = False) -> list[dict]:
        """列出 Skill，可按 status / visibility 过滤。content 默认不返回（体积大）。"""
        async with AsyncSessionLocal() as db:
            stmt = select(SkillDefinition).order_by(SkillDefinition.updated_at.desc())
            if status:
                stmt = stmt.where(SkillDefinition.status == status)
            if visibility:
                stmt = stmt.where(SkillDefinition.visibility == visibility)
            rows = (await db.execute(stmt)).scalars().all()
        return [self._to_dict(r, include_content=include_content) for r in rows]

    async def list_enabled_skills(self) -> list[dict]:
        """供生成流水线使用：只要 enabled 的，并带上 content（要塞进 prompt）。"""
        return await self.list_skills(status="enabled", include_content=True)

    async def get_skill(self, skill_key: str, *, include_content: bool = True) -> dict | None:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(SkillDefinition).where(SkillDefinition.skill_key == skill_key)
            )).scalar_one_or_none()
        return self._to_dict(row, include_content=include_content) if row else None

    # ---------- 写入 ----------

    async def create_or_update_skill(self, data: dict, username: str = "") -> dict:
        """按 skill_key upsert。只覆盖 data 里出现的键，未出现的保留原值。"""
        skill_key = data["skill_key"]
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(SkillDefinition).where(SkillDefinition.skill_key == skill_key)
            )).scalar_one_or_none()
            if row is None:
                row = SkillDefinition(skill_key=skill_key, created_by=username or "system")
                db.add(row)
                row.name = data.get("name") or skill_key
                row.description = data.get("description", "")
                row.version = data.get("version", "1.0.0")
                row.content = data.get("content", "")
                row.bos_path = data.get("bos_path")
                row.status = data.get("status", "enabled")
                row.visibility = data.get("visibility", "internal")
                row.output_type = data.get("output_type", "data")
            else:
                for field in ("name", "description", "version", "content",
                              "bos_path", "status", "visibility", "output_type"):
                    if field in data and data[field] is not None:
                        setattr(row, field, data[field])
            await db.commit()
            await db.refresh(row)
            return self._to_dict(row, include_content=False)

    async def install_skill(self, skill_key: str, username: str = "") -> dict | None:
        """从本地目录安装（解析 SKILL.md → upsert）。目录不存在或无 SKILL.md 返回 None。

        差异：参考的 install 入参是 BOS zip URL；sinan 入参是本地包目录名。
        """
        pkg = skill_package.load_package(skill_key)
        if pkg is None:
            return None
        meta = pkg.pop("meta", {})
        record = await self.create_or_update_skill(pkg, username)
        record["meta"] = meta
        if pkg.get("status") == "failed":
            logger.warning("skill installed without handler: %s", skill_key)
        return record

    async def update_skill_status(self, skill_key: str, status: str,
                                 username: str = "") -> dict | None:
        """启用 / 停用。status 非法直接返回 None，由路由转 400/404。"""
        if status not in VALID_STATUS:
            return None
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(SkillDefinition)
                .where(SkillDefinition.skill_key == skill_key)
                .values(status=status)
            )
            if not result.rowcount:
                await db.rollback()
                return None
            await db.commit()
            row = (await db.execute(
                select(SkillDefinition).where(SkillDefinition.skill_key == skill_key)
            )).scalar_one_or_none()
        return self._to_dict(row, include_content=False) if row else None

    async def enable_skill(self, skill_key: str, username: str = "") -> dict | None:
        return await self.update_skill_status(skill_key, "enabled", username)

    async def disable_skill(self, skill_key: str, username: str = "") -> dict | None:
        return await self.update_skill_status(skill_key, "disabled", username)

    async def delete_skill(self, skill_key: str) -> bool:
        """只删表记录，不动本地包目录（避免误删用户手写的 Skill 源码）。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(SkillDefinition).where(SkillDefinition.skill_key == skill_key)
            )
            if not result.rowcount:
                await db.rollback()
                return False
            await db.commit()
        return True

    # ---------- 启动同步 ----------

    async def sync_enabled_skills(self) -> list[str]:
        """启动时把本地包同步进表：新包按包内声明落库，已存在的包只刷新元信息。

        对齐参考 skill_package.sync_enabled_skills 的**时机**（服务启动），
        但方向相反：参考是「按表里的 enabled 记录去补下载包」，
        sinan 是「按本地包去补表记录」——因为 sinan 的权威来源是文件系统。

        已被人工 disable 的包不会被这次同步重新 enable。
        """
        if not settings.skill_sync_on_startup:
            return []
        synced: list[str] = []
        existing = {s["skill_key"]: s for s in await self.list_skills()}
        for pkg in skill_package.load_all_packages():
            key = pkg["skill_key"]
            pkg.pop("meta", None)
            prior = existing.get(key)
            if prior and prior.get("status") == "disabled":
                pkg["status"] = "disabled"     # 尊重人工停用
            try:
                await self.create_or_update_skill(pkg, "system")
                synced.append(key)
            except Exception:
                logger.exception("sync skill failed: %s", key)
        logger.info("skill sync done: %d local package(s) -> %s", len(synced), synced)
        return synced

    # ---------- 内部 ----------

    def _to_dict(self, row: SkillDefinition, *, include_content: bool) -> dict:
        """ORM → API dict。字段名与参考 _skill_to_dict 一致。"""
        data = {
            "skill_key": row.skill_key,
            "name": row.name,
            "description": row.description or "",
            "version": row.version,
            "status": row.status,
            "visibility": row.visibility,
            "bos_path": row.bos_path,
            "output_type": row.output_type or "data",
            "created_by": row.created_by,
            "updated_by": row.created_by,
            "created_at": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else "",
            "updated_at": row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else "",
        }
        if include_content:
            data["content"] = row.content or ""
        return data


skill_registry = SkillRegistry()