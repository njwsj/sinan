# sinan/api/routes/hosting.py
"""页面托管路由（Step 10 新增）。

对齐参考 page/api/routes/hosting.py:28。

路由列表：
  POST /api/page/host                  — 上传 HTML 或 ZIP
  POST /api/page/pages/{marker}/publish   — 发布指定版本
  POST /api/page/pages/{marker}/unpublish — 取消发布
  POST /api/page/pages/{marker}/rollback  — 回滚 current_version 指针

认证：过渡期暂无，Step 3 统一补充。
"""
from __future__ import annotations

import io
import json
import uuid
import zipfile

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import PageVersion
from sinan.services.page_service import page_service
from sinan.services.page_store import page_store
from sinan.services.security import security_service
from sqlalchemy import select

router = APIRouter(prefix="/api/page", tags=["hosting"])


# ------------------------------------------------------------------ #
# 请求模型                                                              #
# ------------------------------------------------------------------ #

class PublishRequest(BaseModel):
    version: int
    published_to: str = ""


class RollbackRequest(BaseModel):
    version: int


# ------------------------------------------------------------------ #
# 上传托管                                                              #
# ------------------------------------------------------------------ #

@router.post("/host")
async def host_page(
    file: UploadFile = File(...),
    title: str = Form(...),
    marker: str = Form(default=None),
):
    """上传并托管外部 HTML 页面或 ZIP 包。

    对齐参考 page/api/routes/hosting.py:28。
    - 单 HTML 文件：安全扫描通过后写入 page_version，返回预览 URL。
    - ZIP 包：逐条目校验路径、扩展名；对所有 HTML 文件做安全扫描。
    """
    marker = marker or f"page_{uuid.uuid4().hex[:12]}"
    content = await file.read()
    filename = file.filename or "index.html"

    if filename.endswith(".zip"):
        result = await _handle_zip(marker, title, content)
    else:
        result = await _handle_single_html(marker, title, content, filename)

    if result.get("error"):
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": result["error"]},
        )
    return {"code": 0, "data": result}


async def _handle_single_html(
    marker: str, title: str, content: bytes, filename: str
) -> dict:
    code = content.decode("utf-8", errors="replace")
    scan = security_service.scan(code)
    if not scan["passed"]:
        return {
            "error": f"安全扫描未通过: {scan['blocking_issues']} 个阻塞性问题",
            "scan": scan,
        }
    version = await page_store.next_version(marker)
    pv = await page_store.save(
        marker=marker, version=version, html=code,
        created_by="system", title=title, note="manual_upload",
    )
    await _write_scan_result(pv.id, scan)
    return {
        "marker": marker,
        "title": title,
        "version": version,
        "source": "manual",
        "file_count": 1,
        "entry_file": filename,
        "size": len(content),
        "security_scan": scan,
        "preview_url": f"/api/page/preview/{marker}/v{version}",
    }


async def _handle_zip(marker: str, title: str, content: bytes) -> dict:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return {"error": "无效的 ZIP 文件"}

    names = zf.namelist()
    if not any(n == "index.html" or n.endswith("/index.html") for n in names):
        return {"error": "ZIP 包必须包含 index.html"}
    if len(names) > security_service.max_file_count():
        return {"error": f"文件数量超限: {len(names)} > {security_service.max_file_count()}"}

    total_size = sum(info.file_size for info in zf.infolist())
    if total_size > security_service.max_total_size():
        return {"error": f"解压后大小超限: {total_size} > {security_service.max_total_size()}"}

    html_content = ""
    for info in zf.infolist():
        if info.filename.endswith("/"):
            continue  # 目录条目跳过
        err = security_service.validate_zip_entry(info.filename, info.file_size)
        if err:
            return {"error": err}
        if info.filename.endswith(".html"):
            code = zf.read(info.filename).decode("utf-8", errors="replace")
            scan = security_service.scan(code)
            if not scan["passed"]:
                return {
                    "error": f"安全扫描未通过 ({info.filename}): {scan['blocking_issues']} 个问题"
                }
            if info.filename in ("index.html",) or info.filename.endswith("/index.html"):
                html_content = code

    version = await page_store.next_version(marker)
    pv = await page_store.save(
        marker=marker, version=version, html=html_content,
        created_by="system", title=title, note="zip_upload",
    )
    clean_scan = {"passed": True, "issues": [], "total_issues": 0, "blocking_issues": 0}
    await _write_scan_result(pv.id, clean_scan)
    return {
        "marker": marker,
        "title": title,
        "version": version,
        "source": "manual",
        "file_count": len(names),
        "entry_file": "index.html",
        "size": total_size,
        "security_scan": clean_scan,
        "preview_url": f"/api/page/preview/{marker}/v{version}",
    }


async def _write_scan_result(pv_id: int, scan: dict) -> None:
    """回写 page_version.security_scan 和 scan_result（当前无写入点的遗留项）。"""
    async with AsyncSessionLocal() as db:
        pv = (
            await db.execute(select(PageVersion).where(PageVersion.id == pv_id))
        ).scalar_one_or_none()
        if pv:
            # security_scan: 0=未扫 1=通过 2=拦截
            pv.security_scan = 1 if scan["passed"] else 2
            pv.scan_result = json.dumps(scan, ensure_ascii=False)
            await db.commit()


# ------------------------------------------------------------------ #
# 发布 / 取消发布 / 回滚                                                #
# ------------------------------------------------------------------ #

@router.post("/pages/{marker}/publish")
async def publish_page(marker: str, body: PublishRequest):
    """发布指定版本。

    验收：只发布 body.version，不影响 current_version。
    对齐参考：发布逻辑在参考 session.py 内联；sinan 提取为独立端点。
    """
    result = await page_service.publish_page(marker, body.version, body.published_to)
    if not result["ok"]:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": result["error"]},
        )
    return {"code": 0, "data": result}


@router.post("/pages/{marker}/unpublish")
async def unpublish_page(marker: str):
    """取消发布，状态回退到 preview，清 published_version。"""
    result = await page_service.unpublish_page(marker)
    if not result["ok"]:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": result["error"]},
        )
    return {"code": 0, "data": result}


@router.post("/pages/{marker}/rollback")
async def rollback_version(marker: str, body: RollbackRequest):
    """回滚 current_version 指针到指定版本（不删历史版本）。"""
    result = await page_service.rollback_version(marker, body.version)
    if not result["ok"]:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": result["error"]},
        )
    return {"code": 0, "data": result}