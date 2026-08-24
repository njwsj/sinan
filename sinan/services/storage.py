# sinan/services/storage.py
"""StorageBackend 抽象接口与工厂函数。

当前只实现本地文件存储（LocalStorage）。
将来需要接 BOS 时，只新增 bos_storage.py 并把 storage_type 改为 "bos" 即可，
不需要改调用方代码。
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class StorageBackend(Protocol):
    async def put(self, key: str, content: bytes, content_type: str | None = None) -> str:
        """上传内容，返回 storage_uri（本地时形如 local://key）。"""
        ...

    async def get(self, key: str) -> bytes:
        """读取内容，key 不存在时抛 FileNotFoundError。"""
        ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def signed_url(self, key: str, expires: int = 3600) -> str:
        """返回可访问 URL；本地时返回 /api/storage/{key}。"""
        ...


def get_storage() -> StorageBackend:
    """工厂函数：按 settings.storage_type 返回对应实现。"""
    from sinan.config.settings import settings
    # 当前只有 local，以后加 bos 在这里扩展
    from sinan.services.local_storage import LocalStorage
    return LocalStorage(base_dir=settings.storage_base_path)


# 模块级单例，其他模块 from sinan.services.storage import storage 即可
storage: StorageBackend = get_storage()