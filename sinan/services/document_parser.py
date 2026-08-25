# sinan/services/document_parser.py
"""文档解析：把各种格式的字节流变成可注入 prompt 的纯文本。

对齐参考的**目的**（知识库正文归一化 + 清洗 + 限长），实现上只用标准库 + 已有依赖：
  md / txt / json / yaml → 直接解码
  html                   → 去 script/style/标签
  csv / xlsx             → 复用 data_service 的解析器，转 markdown 表格摘要
其他类型退化为「二进制，跳过」，不猜测编码。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_TEXT_EXTS = {".md", ".txt", ".json", ".yaml", ".yml", ".xml", ".log"}
_HTML_EXTS = {".html", ".htm"}
_TABLE_EXTS = {".csv", ".xlsx", ".xls"}
_MAX_TABLE_ROWS = 200


def _strip_html(html: str) -> tuple[str, str]:
    """返回 (title, text)。去掉 script/style，再去标签，合并空白。"""
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    body = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    return title, clean_text(body)


def _table_to_markdown(parsed: dict, name: str) -> str:
    """把 {columns, rows} 转成 markdown 表格（截断到 _MAX_TABLE_ROWS 行）。"""
    columns = [str(c) for c in (parsed.get("columns") or [])]
    rows = parsed.get("rows") or []
    if not columns:
        return ""
    head = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(r.get(c, "")) for c in columns) + " |"
        for r in rows[:_MAX_TABLE_ROWS]
    ]
    note = (f"\n\n（共 {len(rows)} 行，此处只列前 {_MAX_TABLE_ROWS} 行）"
            if len(rows) > _MAX_TABLE_ROWS else "")
    return f"### {name}\n\n" + "\n".join([head, sep, *body]) + note


def clean_text(text: str) -> str:
    """清洗：统一换行、去零宽字符、连续空行压成一个、行尾去空格。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    lines = [line.rstrip() for line in text.split("\n")]
    out: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                out.append("")
            blank = True
            continue
        blank = False
        out.append(re.sub(r"[ \t]{2,}", " ", line))
    return "\n".join(out).strip()


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """按 limit 截断，尽量切在段落边界。返回 (文本, 是否截断)。"""
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    boundary = max(cut.rfind("\n\n"), cut.rfind("\n"))
    if boundary > limit // 2:
        cut = cut[:boundary]
    return cut.rstrip() + "\n\n...(truncated)", True


def parse_bytes(name: str, content: bytes, *, content_type: str = "") -> dict:
    """解析一段字节流，返回 {"title", "text", "parse_type", "error"}。"""
    ext = Path(name).suffix.lower()

    if ext in _HTML_EXTS or "html" in (content_type or ""):
        title, text = _strip_html(content.decode("utf-8", errors="replace"))
        return {"title": title or name, "text": text, "parse_type": "html", "error": ""}

    if ext in _TABLE_EXTS:
        from sinan.services.data_service import _parse_csv, _parse_excel
        try:
            parsed = _parse_csv(content) if ext == ".csv" else _parse_excel(content)
        except Exception as e:
            return {"title": name, "text": "", "parse_type": "table", "error": str(e)}
        return {"title": name, "text": _table_to_markdown(parsed, name),
                "parse_type": "table", "error": ""}

    if ext in _TEXT_EXTS or (content_type or "").startswith("text/") or not ext:
        text = content.decode("utf-8", errors="replace")
        if ext == ".json":
            try:  # JSON 美化一下，LLM 更好读
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        return {"title": name, "text": clean_text(text), "parse_type": "text", "error": ""}

    return {"title": name, "text": "", "parse_type": "binary",
            "error": f"unsupported document type: {ext or content_type or 'unknown'}"}