# sinan/services/data_service.py
import io
import json
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _cell_val(v: Any) -> Any:
    """把 openpyxl 单元格值转成 JSON 可序列化的 Python 原生类型。"""
    if v is None:
        return ""
    # datetime / date / time → isoformat 字符串
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


class DataService:
    """解析 Excel 文件，把完整数据持久化到本地文件，返回轻量元数据。"""

    def _parse_bytes(self, file_data: bytes) -> dict[str, Any]:
        """
        用 openpyxl 解析 Excel，返回：
          {
            "columns": ["col1", "col2", ...],
            "rows": [{"col1": v, ...}, ...],
            "row_count": int
          }
        """
        try:
            from openpyxl import load_workbook
        except ImportError as e:
            raise ValueError("openpyxl 未安装，请执行 pip install openpyxl") from e

        try:
            wb = load_workbook(io.BytesIO(file_data), data_only=True)
        except Exception as e:
            logger.error("load_workbook failed: %s", e)
            raise ValueError(f"Excel 解析失败：{e}") from e

        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if not rows:
            return {"columns": [], "rows": [], "row_count": 0}

        # 第一行作为列名
        columns = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(rows[0])]
        data_rows = [
            {col: _cell_val(val) for col, val in zip(columns, row)}
            for row in rows[1:]
        ]
        return {"columns": columns, "rows": data_rows, "row_count": len(data_rows)}

    async def parse_and_store(
        self, file_data: bytes, storage_dir: str, file_id: str | None = None
    ) -> dict[str, Any]:
        """
        解析 Excel，把完整结果写入 {storage_dir}/{file_id}.json，
        返回轻量元数据（不含完整 rows）：
          {
            "file_id": str,
            "columns": [...],
            "row_count": int,
            "preview": [前 5 行 dict, ...]
          }
        """
        if file_id is None:
            file_id = uuid.uuid4().hex

        parsed = self._parse_bytes(file_data)

        # 持久化完整数据到本地文件
        storage_path = Path(storage_dir)
        storage_path.mkdir(parents=True, exist_ok=True)
        json_file = storage_path / f"{file_id}.json"
        json_file.write_text(
            json.dumps(parsed, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        logger.info("attachment stored: file_id=%s rows=%d", file_id, parsed["row_count"])

        return {
            "file_id": file_id,
            "columns": parsed["columns"],
            "row_count": parsed["row_count"],
            "preview": parsed["rows"][:5],
        }

    async def load(self, storage_dir: str, file_id: str) -> dict[str, Any] | None:
        """从本地文件加载完整解析数据，文件不存在时返回 None。"""
        json_file = Path(storage_dir) / f"{file_id}.json"
        if not json_file.exists():
            logger.warning("attachment not found: file_id=%s", file_id)
            return None
        return json.loads(json_file.read_text(encoding="utf-8"))


data_service = DataService()
