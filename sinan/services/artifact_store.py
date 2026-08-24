# sinan/services/artifact_store.py
"""Artifact 写入与读取服务。

将 harness/orchestrator._save_artifact() 内联实现迁移到此处（Step 9）。
小内容（< 64KB）直接写 generation_artifact.content 列；
大内容（>= 64KB）通过 StorageBackend 存储，DB 只保存路径（bos_path 列）。
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import func, select

from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenerationArtifact
from sinan.services.storage import storage

logger = logging.getLogger(__name__)

_INLINE_LIMIT = 64 * 1024  # 64KB 以内直接入库


class ArtifactStore:

    async def save_artifact(
        self,
        session_id: str,
        artifact_type: str,
        content: dict | str,
        *,
        meta: dict | None = None,
        marker: str | None = None,
    ) -> GenerationArtifact:
        """写一行 GenerationArtifact，version 按 (session_id, artifact_type) 递增。

        - 小内容 → content 列（直接入库）
        - 大内容 → LocalStorage 写文件，bos_path 列记路径；失败时 fallback 到 inline
        """
        content_str = (
            json.dumps(content, ensure_ascii=False)
            if isinstance(content, dict)
            else str(content)
        )
        content_bytes = content_str.encode("utf-8")

        async with AsyncSessionLocal() as db:
            current = await db.execute(
                select(func.coalesce(func.max(GenerationArtifact.version), 0)).where(
                    GenerationArtifact.session_id == session_id,
                    GenerationArtifact.artifact_type == artifact_type,
                )
            )
            version = int(current.scalar() or 0) + 1

            bos_path: str | None = None
            inline_content: str | None = None

            if len(content_bytes) <= _INLINE_LIMIT:
                inline_content = content_str
            else:
                key = f"artifacts/{marker or session_id}/{artifact_type}_v{version}.json"
                try:
                    uri = await storage.put(key, content_bytes, "application/json")
                    bos_path = uri   # 形如 local://artifacts/...
                    logger.info("artifact 卸载到存储: key=%s size=%d", key, len(content_bytes))
                except Exception as e:
                    logger.warning("artifact 存储失败，fallback inline: %s", e)
                    inline_content = content_str

            artifact_meta = dict(meta or {})
            if isinstance(content, dict):
                artifact_meta.setdefault("format", content.get("_format", "json"))

            record = GenerationArtifact(
                session_id=session_id,
                artifact_type=artifact_type,
                version=version,
                content=inline_content,
                bos_path=bos_path,
                meta=artifact_meta,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

        logger.info(
            "artifact saved: session=%s type=%s version=%d mode=%s",
            session_id, artifact_type, version,
            "inline" if inline_content else "storage",
        )
        return record

    async def get_artifact(
        self,
        session_id: str,
        artifact_type: str,
        version: int | None = None,
    ) -> dict | None:
        """读取 artifact 内容，自动从 DB 列或 LocalStorage 获取。"""
        async with AsyncSessionLocal() as db:
            if version is not None:
                stmt = select(GenerationArtifact).where(
                    GenerationArtifact.session_id == session_id,
                    GenerationArtifact.artifact_type == artifact_type,
                    GenerationArtifact.version == version,
                )
            else:
                stmt = (
                    select(GenerationArtifact)
                    .where(
                        GenerationArtifact.session_id == session_id,
                        GenerationArtifact.artifact_type == artifact_type,
                    )
                    .order_by(GenerationArtifact.version.desc())
                    .limit(1)
                )
            record = (await db.execute(stmt)).scalar_one_or_none()

        if record is None:
            return None

        if record.content:
            try:
                return json.loads(record.content)
            except json.JSONDecodeError:
                return {"raw": record.content}

        if record.bos_path:
            # 去掉 local:// 前缀取出真正的 key
            key = record.bos_path.removeprefix("local://")
            try:
                data = await storage.get(key)
                return json.loads(data.decode("utf-8"))
            except Exception as e:
                logger.warning("artifact 存储读取失败: key=%s err=%s", key, e)
                return None

        return None

    async def list_artifacts(self, session_id: str) -> list[GenerationArtifact]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenerationArtifact)
                .where(GenerationArtifact.session_id == session_id)
                .order_by(GenerationArtifact.artifact_type, GenerationArtifact.version)
            )
            return list(result.scalars().all())

    async def save_code_snapshot(
        self,
        session_id: str,
        code: str,
        *,
        marker: str | None = None,
    ) -> GenerationArtifact:
        """存储代码快照（artifact_type='code'）。"""
        return await self.save_artifact(
            session_id, "code",
            {"code": code, "_format": "html"},
            marker=marker,
        )


artifact_store = ArtifactStore()