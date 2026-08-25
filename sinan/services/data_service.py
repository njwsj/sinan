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

# ─── Step 12：数据源解析 ─────────────────────────────
_DS_PREFIXES = {"mock:": "mock", "file:": "file", "api:": "api",
                "db:": "database", "static:": "static"}


def parse_datasource_ref(ref: str, index: int = 0) -> "DataSourceConfig":
    """把请求里的一个 datasource 字符串解析成 DataSourceConfig。

    支持写法：
      mock:mock-metrics?months=6     → mock，params 从 query 串取
      file:sales.csv                 → file，路径在 knowledge_dir 下解析
      api:https://host/path          → api
      https://host/path              → api（裸 URL）
      db:select 1                    → database（当前不支持执行，返回 unsupported）
      static:{"columns":[],"rows":[]} → static，内联 JSON
      其他                            → file（当作相对路径）
    """
    from urllib.parse import parse_qsl, urlparse

    from sinan.config.settings import settings as _settings
    from sinan.models.contracts import DataSourceConfig

    raw = (ref or "").strip()
    ds_type = "file"
    body = raw
    for prefix, typ in _DS_PREFIXES.items():
        if raw.lower().startswith(prefix):
            ds_type, body = typ, raw[len(prefix):]
            break
    else:
        if raw.startswith(("http://", "https://")):
            ds_type = "api"

    cfg = DataSourceConfig(
        type=ds_type, ref=raw, name=f"{ds_type}_{index + 1}",
        timeout=_settings.datasource_timeout_seconds,
        error_policy=_settings.datasource_error_policy,
    )
    if ds_type == "api":
        cfg.endpoint = body
        cfg.name = urlparse(body).path.strip("/").split("/")[-1] or cfg.name
    elif ds_type == "mock":
        parsed = urlparse(body)
        cfg.name = parsed.path or "mock"
        cfg.params = dict(parse_qsl(parsed.query))
    elif ds_type == "database":
        cfg.query = body
    elif ds_type == "static":
        try:
            cfg.sample_data = json.loads(body)
        except json.JSONDecodeError:
            cfg.sample_data = None
    else:
        cfg.path = body
        cfg.name = Path(body).name or cfg.name
    return cfg


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
    # ─── Step 12：数据源取数 ───────────────────────────

    async def resolve_datasources(self, refs: list[str]) -> dict:
        """把请求里的 datasources 字符串列表解析并取数。

        每条结果都带 schema / sample_data / fetch 方式 / 超时 / 错误策略（计划 12.4 五要素）。
        error_policy='ignore'（默认）时失败只记录；'fail' 时抛 ValueError 让 Job 失败。
        """
        cleaned = [str(r).strip() for r in (refs or []) if str(r).strip()]
        if not cleaned:
            return {"items": [], "ok_count": 0}

        items: list[dict] = []
        for idx, ref in enumerate(cleaned):
            cfg = parse_datasource_ref(ref, idx)
            item = await self._fetch_datasource(cfg)
            items.append(item)
            if not item["ok"] and cfg.error_policy == "fail":
                raise ValueError(f"数据源 {cfg.name} 取数失败：{item['error']}")
        result = {"items": items, "ok_count": sum(1 for i in items if i["ok"])}
        logger.info("datasources resolved: %d/%d ok", result["ok_count"], len(items))
        return result

    async def _fetch_datasource(self, cfg) -> dict:
        """按类型取数，统一返回结构。任何异常都收敛成 ok=False。"""
        base = {"name": cfg.name, "type": cfg.type, "ref": cfg.ref,
                "ok": False, "error": "", "data_schema": {}, "sample_data": None}
        try:
            if cfg.type == "static":
                parsed = cfg.sample_data or {}
            elif cfg.type == "mock":
                parsed = self._mock_rows(cfg)
            elif cfg.type == "file":
                parsed = await self._file_rows(cfg)
            elif cfg.type == "api":
                parsed = await self._api_rows(cfg)
            elif cfg.type == "database":
                base["error"] = ("database 类型数据源在 sinan 中不支持执行"
                                 "（学习项目不接真实库），请改用 file / static / mock")
                return base
            else:
                base["error"] = f"unknown datasource type: {cfg.type}"
                return base
        except Exception as e:
            base["error"] = f"{type(e).__name__}: {e}"
            return base

        rows = parsed.get("rows") or []
        columns = parsed.get("columns") or (list(rows[0].keys()) if rows else [])
        base.update({
            "ok": bool(columns or rows),
            "data_schema": {c: self._infer_type(rows[0].get(c)) for c in columns} if rows else {},
            "sample_data": {"columns": columns, "rows": rows,
                            "row_count": parsed.get("row_count", len(rows))},
        })
        if not base["ok"]:
            base["error"] = "数据源返回空数据"
        return base

    def _mock_rows(self, cfg) -> dict:
        """内置 mock 取数：确定性造 n 行两列数据，仅用于链路验证。"""
        try:
            count = int(cfg.params.get("rows") or cfg.params.get("months") or 6)
        except (TypeError, ValueError):
            count = 6
        count = max(1, min(count, 100))
        rows = [{"label": f"item-{i + 1}", "value": 100 + 10 * i} for i in range(count)]
        return {"columns": ["label", "value"], "rows": rows, "row_count": count}

    async def _file_rows(self, cfg) -> dict:
        """从 knowledge_dir 下读本地文件并解析（csv/xlsx/json）。"""
        from sinan.services.document_parser import parse_bytes
        from sinan.services.knowledge_context import _resolve_local

        path = _resolve_local(cfg.path or "")
        if not path.is_file():
            raise FileNotFoundError(f"数据源文件不存在：{path}")
        content = path.read_bytes()
        ext = path.suffix.lower()
        if ext == ".csv":
            return _parse_csv(content)
        if ext in (".xlsx", ".xls"):
            return _parse_excel(content)
        if ext == ".json":
            data = json.loads(content.decode("utf-8", errors="replace"))
            if isinstance(data, list):
                return {"columns": list(data[0].keys()) if data else [],
                        "rows": data, "row_count": len(data)}
            return data if isinstance(data, dict) else {"rows": []}
        parsed = parse_bytes(path.name, content)
        return {"columns": [], "rows": [], "row_count": 0, "text": parsed["text"]}

    async def _api_rows(self, cfg) -> dict:
        """api 类型：GET endpoint，期望 JSON。带超时，不带任何凭证。"""
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(cfg.timeout)) as client:
            resp = await client.get(cfg.endpoint or "")
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, list):
            return {"columns": list(data[0].keys()) if data else [],
                    "rows": data, "row_count": len(data)}
        if isinstance(data, dict):
            rows = data.get("rows") or data.get("data") or []
            if isinstance(rows, list):
                return {"columns": data.get("columns") or (list(rows[0].keys()) if rows else []),
                        "rows": rows, "row_count": len(rows)}
        return {"columns": [], "rows": [], "row_count": 0}

    @staticmethod
    def _infer_type(value) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        return "string"


data_service = DataService()