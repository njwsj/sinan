# sinan/services/local_storage.py
"""本地文件系统 StorageBackend 实现。"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalStorage:
    """以 base_dir 为根目录的本地文件存储。"""

    def __init__(self, base_dir: str = "./output/storage"):
        self._base = Path(base_dir).resolve()

    def _safe_path(self, key: str) -> Path:
        """解析路径，防止路径穿越（../../../etc 这类攻击）。"""
        p = (self._base / key).resolve()
        if not (p == self._base or self._base in p.parents):
            raise ValueError(f"路径穿越被拒绝: key={key!r}")
        return p

    async def put(self, key: str, content: bytes, content_type: str | None = None) -> str:
        p = self._safe_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        logger.debug("LocalStorage.put: key=%s size=%d", key, len(content))
        return f"local://{key}"

    async def get(self, key: str) -> bytes:
        p = self._safe_path(key)
        if not p.exists():
            raise FileNotFoundError(f"LocalStorage: 文件不存在 key={key!r}")
        return p.read_bytes()

    async def delete(self, key: str) -> None:
        p = self._safe_path(key)
        if p.exists():
            p.unlink()

    async def exists(self, key: str) -> bool:
        try:
            return self._safe_path(key).exists()
        except ValueError:
            return False

    async def signed_url(self, key: str, expires: int = 3600) -> str:
        # 本地模式返回内部 API 路径（Step 10 注册 /api/storage/ 路由时使用）
        return f"/api/storage/{key}"