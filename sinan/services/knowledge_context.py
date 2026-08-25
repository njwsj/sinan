# sinan/services/knowledge_context.py
"""知识库上下文：校验 → 读取 → 解析 → 限长 → 清洗 → 落 Artifact → 注入 state。

流程与计划 12.3 完全一致，只把「抓取」的默认实现从 HTTP 换成本地文件：
  - 本地文件（推荐）：settings.knowledge_dir 下的相对路径，或 file:// URI；
    做 realpath 归一化 + 前缀校验，防目录穿越；
  - HTTP：默认关闭（settings.knowledge_allow_http=False）。开启后保留参考的 SSRF 校验
    （拒绝 localhost / 私网 / link-local）和字节上限。

产出：
  {"items": [...], "text": "合并正文", "ok_count": n, "chars": m}
并把完整内容写成 artifact_type="knowledge" 的 Artifact（Step 9 的 artifact_store）。
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import unquote, urlparse

from sinan.config.settings import settings
from sinan.models import events
from sinan.services import document_parser
from sinan.services.artifact_store import artifact_store
from sinan.services.generation_event_bus import event_bus

logger = logging.getLogger(__name__)

_MAX_HTTP_BYTES = 1024 * 1024      # 1MB，对齐参考 MAX_WEBFETCH_BYTES

# 项目根目录（sinan/services/knowledge_context.py → parents[2]）。
# 与 skill_package 一致：相对路径按项目根解析，不按 Path.cwd()。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def knowledge_root() -> Path:
    """本地知识库根目录（绝对路径）。所有本地知识源都必须落在这个目录下。"""
    p = Path(settings.knowledge_dir).expanduser()
    return p.resolve() if p.is_absolute() else (_PROJECT_ROOT / p).resolve()


def _resolve_local(source: str) -> Path:
    """把一个本地引用解析成 knowledge_dir 下的绝对路径。越界抛 ValueError。"""
    raw = source
    if raw.startswith("file://"):
        raw = unquote(urlparse(raw).path)
    root = knowledge_root()
    candidate = Path(raw).expanduser()
    target = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if root not in target.parents and target != root:
        raise ValueError(f"路径越界，只允许读取 {root} 下的文件：{source}")
    return target


def _is_public_http(url: str) -> tuple[bool, str]:
    """SSRF 校验：只放行公网 http/https 主机。返回 (是否放行, 原因)。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"unsupported scheme: {parsed.scheme}"
    host = parsed.hostname or ""
    if not host or host.lower() in ("localhost", "localhost.localdomain"):
        return False, "localhost is not allowed"
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        return False, f"dns resolve failed: {e}"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f"private address is not allowed: {ip}"
    return True, ""


async def _read_source(source: str) -> dict:
    """读一个来源，返回 {"name", "bytes", "content_type", "error"}。"""
    if source.startswith(("http://", "https://")):
        if not settings.knowledge_allow_http:
            return {"name": source, "bytes": b"", "content_type": "",
                    "error": "HTTP 知识源已禁用（settings.knowledge_allow_http=False），"
                             "请改为放入本地 knowledge 目录"}
        allowed, reason = _is_public_http(source)
        if not allowed:
            return {"name": source, "bytes": b"", "content_type": "", "error": reason}
        import httpx
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.knowledge_fetch_timeout),
                follow_redirects=True,
            ) as client:
                resp = await client.get(source)
                resp.raise_for_status()
                content = resp.content[:_MAX_HTTP_BYTES]
            name = Path(urlparse(source).path).name or "index.html"
            return {"name": name, "bytes": content,
                    "content_type": resp.headers.get("content-type", ""), "error": ""}
        except Exception as e:
            return {"name": source, "bytes": b"", "content_type": "", "error": f"fetch failed: {e}"}

    try:
        path = _resolve_local(source)
    except ValueError as e:
        return {"name": source, "bytes": b"", "content_type": "", "error": str(e)}
    if not path.is_file():
        return {"name": source, "bytes": b"", "content_type": "",
                "error": f"文件不存在：{path}"}
    try:
        return {"name": path.name, "bytes": path.read_bytes(),
                "content_type": "", "error": ""}
    except OSError as e:
        return {"name": path.name, "bytes": b"", "content_type": "",
                "error": f"read failed: {e}"}


async def load_knowledge_sources(sources: list[str], *, session_id: str,
                                 marker: str | None = None) -> dict:
    """摄取全部知识源。逐条发 knowledge_source 事件，整体落一条 Artifact。

    单条失败不影响其他条目，也不阻断流水线——与参考的 best-effort 策略一致。
    """
    cleaned = [str(s).strip() for s in (sources or []) if str(s).strip()]
    if not cleaned:
        return {"items": [], "text": "", "ok_count": 0, "chars": 0}

    items: list[dict] = []
    chunks: list[str] = []
    for source in cleaned:
        raw = await _read_source(source)
        if raw["error"]:
            items.append({"source": source, "ok": False, "title": "",
                          "chars": 0, "error": raw["error"]})
        else:
            parsed = document_parser.parse_bytes(
                raw["name"], raw["bytes"], content_type=raw["content_type"]
            )
            text, truncated = document_parser.truncate(
                parsed["text"], settings.knowledge_max_chars
            )
            ok = bool(text) and not parsed["error"]
            items.append({"source": source, "ok": ok, "title": parsed["title"],
                          "chars": len(text), "error": parsed["error"],
                          "parse_type": parsed["parse_type"], "truncated": truncated})
            if ok:
                chunks.append(f"### 知识来源：{parsed['title'] or source}\n\n{text}")

        last = items[-1]
        if session_id:
            await event_bus.publish(
                session_id, events.KNOWLEDGE_SOURCE,
                events.knowledge_source_data(
                    source, last["ok"], title=last.get("title", ""),
                    chars=last.get("chars", 0), error=last.get("error", ""),
                ),
                marker=marker,
            )

    combined, _ = document_parser.truncate(
        "\n\n---\n\n".join(chunks), settings.knowledge_total_max_chars
    )
    result = {
        "items": items,
        "text": combined,
        "ok_count": sum(1 for i in items if i["ok"]),
        "chars": len(combined),
    }

    if session_id and combined:
        try:
            await artifact_store.save_artifact(
                session_id, "knowledge",
                {"_format": "markdown", "_content": combined, "items": items},
                marker=marker,
            )
        except Exception:
            logger.exception("save knowledge artifact failed: session=%s", session_id)

    logger.info("knowledge loaded: session=%s ok=%d/%d chars=%d",
                session_id, result["ok_count"], len(items), result["chars"])
    return result