# sinan/services/data_service.py
import csv
import hashlib
import io
import json
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_IMAGE_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def is_supported_image(filename: str, content_type: str) -> bool:
    ext = Path(filename).suffix.lower()
    return content_type in _IMAGE_TYPES or ext in _IMAGE_EXTS


def _cell_val(v: Any) -> Any:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (int, float, bool)):
        return v
    return str(v)


def _parse_excel(content: bytes) -> dict:
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ValueError("openpyxl 未安装，请执行 pip install openpyxl")
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise ValueError(f"Excel 解析失败：{e}") from e
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return {"columns": [], "rows": [], "row_count": 0}
    columns = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(rows[0])]
    data_rows = [
        {col: _cell_val(val) for col, val in zip(columns, row)}
        for row in rows[1:]
    ]
    return {"columns": columns, "rows": data_rows, "row_count": len(data_rows)}


def _parse_csv(content: bytes) -> dict:
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    columns = list(reader.fieldnames or [])
    data_rows = [dict(row) for row in reader]
    return {"columns": columns, "rows": data_rows, "row_count": len(data_rows)}


class DataService:
    """解析附件文件，持久化到 LocalStorage，返回统一元数据。"""

    async def parse_and_store(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
        *,
        file_id: str | None = None,
        session_id: str | None = None,
        marker: str | None = None,
    ) -> dict[str, Any]:
        """解析文件并存储，返回统一格式：
        {
          "file_id", "filename", "content_type",
          "storage_uri",      # 解析结果的存储 URI
          "raw_storage_uri",  # 原始文件的存储 URI
          "sha256",
          "parse_type",       # excel / csv / image / text / binary
          "status": "ready",
          "columns", "row_count", "preview"  # 仅 excel/csv 有
        }
        """
        from sinan.services.storage import storage

        if file_id is None:
            file_id = uuid.uuid4().hex[:16]

        sha256 = hashlib.sha256(file_data).hexdigest()
        prefix = marker or session_id or ("tmp_" + file_id)
        ext = Path(filename).suffix.lower() if "." in filename else ""

        # —— 解析 ——
        parsed: dict | None = None
        parse_type = "binary"
        excel_types = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        )
        if content_type in excel_types or ext in (".xlsx", ".xls"):
            parsed = _parse_excel(file_data)
            parse_type = "excel"
        elif content_type == "text/csv" or ext == ".csv":
            parsed = _parse_csv(file_data)
            parse_type = "csv"
        elif is_supported_image(filename, content_type):
            parse_type = "image"  # 图片不在上传时解析，推迟到 generate 时
        elif content_type.startswith("text/") or ext in (".txt", ".md", ".json", ".xml", ".yaml", ".yml", ".html"):
            parsed = {"text": file_data.decode("utf-8", errors="replace")}
            parse_type = "text"

        # —— 存储原始文件 ——
        safe_ext = ext.lstrip(".") or "raw"
        raw_key = f"attachments/{prefix}/{file_id}.{safe_ext}"
        raw_uri: str | None = None
        try:
            raw_uri = await storage.put(raw_key, file_data, content_type or "application/octet-stream")
        except Exception as e:
            logger.warning("原始文件存储失败 file_id=%s: %s", file_id, e)

        # —— 存储解析结果 ——
        parsed_uri: str | None = None
        if parsed is not None:
            parsed_key = f"attachments/{prefix}/{file_id}.parsed.json"
            try:
                parsed_bytes = json.dumps(parsed, ensure_ascii=False, default=str).encode("utf-8")
                parsed_uri = await storage.put(parsed_key, parsed_bytes, "application/json")
            except Exception as e:
                logger.warning("解析结果存储失败 file_id=%s: %s", file_id, e)

        meta: dict[str, Any] = {
            "file_id": file_id,
            "filename": filename,
            "content_type": content_type,
            "storage_uri": parsed_uri or raw_uri or "",
            "raw_storage_uri": raw_uri or "",
            "sha256": sha256,
            "parse_type": parse_type,
            "status": "ready",
        }
        if parsed is not None and parse_type in ("excel", "csv"):
            meta["columns"] = parsed.get("columns", [])
            meta["row_count"] = parsed.get("row_count", 0)
            meta["preview"] = parsed.get("rows", [])[:5]

        logger.info("attachment processed: file_id=%s type=%s sha256=%s...", file_id, parse_type, sha256[:12])
        return meta

    async def load_parsed(self, storage_uri: str) -> dict[str, Any] | None:
        """从 LocalStorage 读取已存储的解析结果。"""
        from sinan.services.storage import storage
        if not storage_uri:
            return None
        key = storage_uri.removeprefix("local://")
        try:
            data = await storage.get(key)
            return json.loads(data.decode("utf-8"))
        except Exception as e:
            logger.warning("load_parsed 失败 uri=%s: %s", storage_uri, e)
            return None

    # —— 旧接口：仅供 /api/v1/data/upload 过渡期使用 ——

    async def parse_and_store_legacy(
        self, file_data: bytes, storage_dir: str, file_id: str | None = None
    ) -> dict[str, Any]:
        if file_id is None:
            file_id = uuid.uuid4().hex
        parsed = _parse_excel(file_data)
        p = Path(storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{file_id}.json").write_text(
            json.dumps(parsed, ensure_ascii=False, default=str), encoding="utf-8"
        )
        logger.info("attachment stored (legacy): file_id=%s rows=%d", file_id, parsed["row_count"])
        return {
            "file_id": file_id,
            "columns": parsed["columns"],
            "row_count": parsed["row_count"],
            "preview": parsed["rows"][:5],
        }

    async def load(self, storage_dir: str, file_id: str) -> dict[str, Any] | None:
        """旧接口：从本地文件加载。"""
        json_file = Path(storage_dir) / f"{file_id}.json"
        if not json_file.exists():
            return None
        return json.loads(json_file.read_text(encoding="utf-8"))


data_service = DataService()