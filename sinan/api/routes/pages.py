# sinan/api/routes/pages.py
"""Pages 资源路由（Step 10 填充完整端点）。

对齐参考 page/api/routes/pages.py。
认证：过渡期暂无，待 Step 3。

路由：
  GET /api/page/pages/{marker}/versions
  GET /api/page/pages/{marker}/data
  GET /api/page/pages/{marker}/download/{file_id}
  GET /api/page/pages/{marker}/messages
  GET /api/page/pages/{marker}/artifacts
  GET /api/page/pages/{marker}/artifacts/{artifact_type:path}
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import (
    Attachment,
    GenSession,
    GenerationArtifact,
    Page,
    PageVersion,
)

router = APIRouter(prefix="/api/page", tags=["pages"])


# ------------------------------------------------------------------ #
# 版本列表
# ------------------------------------------------------------------ #

@router.get("/pages/{marker}/versions")
async def list_page_versions(marker: str):
    """列出 marker 下所有版本元数据（不含 html_content）。

    对齐参考 pages.py:18，响应格式 {"code": 0, "data": {...}}。
    """
    async with AsyncSessionLocal() as db:
        page = (
            await db.execute(select(Page).where(Page.marker == marker))
        ).scalar_one_or_none()
        versions = list(
            (
                await db.execute(
                    select(PageVersion)
                    .where(PageVersion.marker == marker)
                    .order_by(PageVersion.version.desc())
                )
            ).scalars().all()
        )

    current = page.current_version if page else (versions[0].version if versions else 0)
    return {
        "code": 0,
        "data": {
            "marker": marker,
            "status": page.status if page else None,
            "current_version": current,
            "published_version": page.published_version if page else None,
            "versions": [
                {
                    "version": v.version,
                    "content_hash": v.content_hash,
                    "code_size": v.code_size,
                    "harness_score": v.harness_score,
                    "repair_rounds": v.repair_rounds,
                    "security_scan": v.security_scan,
                    "note": v.note,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in versions
            ],
        },
    }


# ------------------------------------------------------------------ #
# 附件列表（data）
# ------------------------------------------------------------------ #

@router.get("/pages/{marker}/data")
async def get_page_data(marker: str):
    """获取 marker 关联的附件列表。

    对齐参考 pages.py:41（通过 marker → session 反查）。
    """
    async with AsyncSessionLocal() as db:
        session_ids = list(
            (
                await db.execute(
                    select(GenSession.session_id).where(
                        GenSession.marker == marker,
                        GenSession.is_deleted == 0,
                    )
                )
            ).scalars().all()
        )
        if not session_ids:
            return {"code": 0, "data": []}

        attachments = list(
            (
                await db.execute(
                    select(Attachment).where(
                        Attachment.session_id.in_(session_ids)
                    )
                )
            ).scalars().all()
        )

    return {
        "code": 0,
        "data": [
            {
                "file_id": a.file_id,
                "file_name": a.file_name,
                "file_type": a.file_type,
                "file_size": a.file_size,
                "row_count": a.row_count,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in attachments
        ],
    }


# ------------------------------------------------------------------ #
# 附件下载
# ------------------------------------------------------------------ #

@router.get("/pages/{marker}/download/{file_id}")
async def download_page_attachment(marker: str, file_id: str):
    """下载附件原始文件（或解析后 JSON）。

    对齐参考 pages.py:48。
    """
    from sinan.services.storage import storage

    async with AsyncSessionLocal() as db:
        att = (
            await db.execute(
                select(Attachment).where(Attachment.file_id == file_id)
            )
        ).scalar_one_or_none()

    if att is None:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "附件不存在"},
        )

    if att.storage_path:
        key = att.storage_path.removeprefix("local://")
        try:
            data = await storage.get(key)
            return Response(
                content=data,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{att.file_name}"'
                },
            )
        except FileNotFoundError:
            pass

    return JSONResponse(
        status_code=404,
        content={"code": 404, "message": "附件文件不在存储中"},
    )


# ------------------------------------------------------------------ #
# 会话消息
# ------------------------------------------------------------------ #

@router.get("/pages/{marker}/messages")
async def get_page_messages(marker: str):
    """获取 marker 关联的所有会话消息。

    对齐参考 pages.py:67。
    """
    async with AsyncSessionLocal() as db:
        sessions = list(
            (
                await db.execute(
                    select(GenSession)
                    .where(
                        GenSession.marker == marker,
                        GenSession.is_deleted == 0,
                    )
                    .order_by(GenSession.created_at)
                )
            ).scalars().all()
        )

    all_messages: list = []
    for s in sessions:
        if s.messages:
            msgs = s.messages if isinstance(s.messages, list) else []
            all_messages.extend(msgs)

    return {"code": 0, "data": all_messages}


# ------------------------------------------------------------------ #
# 流水线产物列表
# ------------------------------------------------------------------ #

@router.get("/pages/{marker}/artifacts")
async def get_page_artifacts(marker: str):
    """获取 marker 关联的所有流水线产物列表。

    对齐参考 pages.py:74。
    """
    async with AsyncSessionLocal() as db:
        session_ids = list(
            (
                await db.execute(
                    select(GenSession.session_id).where(
                        GenSession.marker == marker,
                        GenSession.is_deleted == 0,
                    )
                )
            ).scalars().all()
        )
        if not session_ids:
            return {"code": 0, "data": []}

        artifacts = list(
            (
                await db.execute(
                    select(GenerationArtifact)
                    .where(
                        GenerationArtifact.session_id.in_(session_ids),
                        GenerationArtifact.is_deleted == 0,
                    )
                    .order_by(
                        GenerationArtifact.artifact_type,
                        GenerationArtifact.version.desc(),
                    )
                )
            ).scalars().all()
        )

    return {
        "code": 0,
        "data": [
            {
                "session_id": a.session_id,
                "artifact_type": a.artifact_type,
                "version": a.version,
                "has_content": bool(a.content or a.bos_path),
                "meta": a.meta,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in artifacts
        ],
    }


# ------------------------------------------------------------------ #
# 流水线产物下载
# ------------------------------------------------------------------ #

@router.get("/pages/{marker}/artifacts/{artifact_type:path}")
async def download_page_artifact(
        marker: str,
        artifact_type: str,
        version: int | None = None,
):
    """下载特定产物内容（JSON），可选指定 version。

    对齐参考 pages.py:81（参考返回 markdown；sinan 返回 JSON，Step 15 对照时豁免）。
    """
    from sinan.services.artifact_store import artifact_store

    async with AsyncSessionLocal() as db:
        session_ids = list(
            (
                await db.execute(
                    select(GenSession.session_id).where(
                        GenSession.marker == marker,
                        GenSession.is_deleted == 0,
                    )
                )
            ).scalars().all()
        )

    if not session_ids:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "未找到相关产物"},
        )

    # 按最近 session 倒序查找
    content = None
    for sid in reversed(session_ids):
        content = await artifact_store.get_artifact(sid, artifact_type, version)
        if content is not None:
            break

    if content is None:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": f"产物 {artifact_type!r} 不存在"},
        )

    type_names = {
        "analysis": "需求分析",
        "design": "设计方案",
        "verification": "验证报告",
        "code": "页面代码",
    }
    filename = type_names.get(artifact_type, artifact_type) + ".json"
    return Response(
        content=json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )