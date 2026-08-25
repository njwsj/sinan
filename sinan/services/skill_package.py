# sinan/services/skill_package.py
"""本地 Skill 包的发现与解析。

对齐参考 page/services/skill_package.py 的**职责**（把包准备好、把 SKILL.md 解析成
可落库的字段），但有意替换了**来源**：
  - 参考：download_zip(BOS URL) → safe_extract_zip → ensure_skill_permissions
  - sinan：直接扫描 settings.skills_dir 下的目录，不下载、不解压、不 chmod

保留的语义：
  - skill_key = 目录名（参考是从 zip 文件名派生）
  - SKILL.md frontmatter 提供 name / description / output_type
  - 正文压缩到 12000 字符以内作为 skill_definition.content（参考 _compact_skill_content）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sinan.config.settings import settings

logger = logging.getLogger(__name__)

SKILL_MD = "SKILL.md"
SKILL_META = ".skill-meta.json"
_CONTENT_LIMIT = 12000
_HANDLER_CANDIDATES = ("handler.py", "scripts/handler.py", "bin/handler.py")

# 项目根目录（sinan/services/skill_package.py → parents[2]）。
# 相对路径按项目根解析而不是 Path.cwd()，这样从任意工作目录启动服务都能找到包，
# 与参考 page/services/skill_package.py:18 的 _PROJECT_ROOT 同思路。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def skills_root() -> Path:
    """Skill 包根目录（绝对路径）。不存在时不创建，由调用方决定要不要建。"""
    p = Path(settings.skills_dir).expanduser()
    return p.resolve() if p.is_absolute() else (_PROJECT_ROOT / p).resolve()


def skill_dir(skill_key: str) -> Path:
    """单个 Skill 的安装目录。skill_key 里的路径分隔符一律拒绝，防目录穿越。"""
    if not skill_key or "/" in skill_key or "\\" in skill_key or skill_key.startswith("."):
        raise ValueError(f"invalid skill_key: {skill_key!r}")
    return skills_root() / skill_key


def list_local_packages() -> list[str]:
    """列出本地所有含 SKILL.md 的包目录名。"""
    root = skills_root()
    if not root.is_dir():
        logger.info("skills dir not found: %s", root)
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / SKILL_MD).is_file()
    )


def resolve_handler(skill_key: str) -> Path | None:
    """找到包内可执行入口（handler.py）。找不到返回 None，注册时标 failed。"""
    base = skill_dir(skill_key)
    for rel in _HANDLER_CANDIDATES:
        candidate = base / rel
        if candidate.is_file():
            return candidate
    return None


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """解析 SKILL.md 头部 YAML frontmatter。逻辑与参考 admin_skills._parse_frontmatter 一致。"""
    if not text.startswith("---"):
        return {}, text.strip()
    lines = text.splitlines()
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}, text.strip()
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key:
            meta[key] = value.strip().strip("\"'")
    return meta, "\n".join(lines[end + 1:]).strip()


def compact_content(body: str, limit: int = _CONTENT_LIMIT) -> str:
    """压缩 SKILL.md 正文：合并连续空行，超长时在章节边界截断。对齐参考实现。"""
    if not body:
        return ""
    out: list[str] = []
    blank = False
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if not blank:
                out.append("")
            blank = True
            continue
        blank = False
        out.append(line)
    content = "\n".join(out).strip()
    if len(content) <= limit:
        return content
    cut = content[:limit]
    boundary = max(cut.rfind("\n## "), cut.rfind("\n# "), cut.rfind("\n\n"))
    if boundary > limit // 2:
        cut = cut[:boundary]
    return cut.rstrip() + "\n\n..."


def _split_keywords(meta: dict[str, str], description: str, skill_key: str) -> list[str]:
    """路由关键词：优先 frontmatter 的 keywords，缺省时从 description 的「触发词:」段提取。"""
    raw = meta.get("keywords") or ""
    if not raw and "触发词" in description:
        tail = description.split("触发词", 1)[1].lstrip("：:")
        raw = tail.split("。", 1)[0]
    parts = [p.strip() for p in raw.replace("、", ",").replace("/", ",").split(",")]
    keywords = [p for p in parts if p]
    keywords.append(skill_key)
    # 去重且保持顺序
    seen: set[str] = set()
    return [k for k in keywords if not (k.lower() in seen or seen.add(k.lower()))]


def load_package(skill_key: str) -> dict | None:
    """读取一个本地包，返回可直接喂给 skill_registry.create_or_update_skill 的 dict。

    返回字段与参考 _install_skill 的 data 一致（多出 meta 一项，用于路由和执行）：
      skill_key / name / description / version / content / bos_path / status / output_type / meta
    """
    base = skill_dir(skill_key)
    md_path = base / SKILL_MD
    if not md_path.is_file():
        logger.warning("SKILL.md missing: %s", md_path)
        return None
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("read SKILL.md failed: %s: %s", md_path, e)
        return None

    meta, body = parse_frontmatter(text)

    description = meta.get("description") or meta.get("summary") or ""
    if not description:
        for line in body.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                description = stripped
                break

    version = meta.get("version") or "1.0.0"
    pkg_meta_path = base / SKILL_META
    if pkg_meta_path.is_file():
        try:
            pkg_meta = json.loads(pkg_meta_path.read_text(encoding="utf-8"))
            version = str(pkg_meta.get("version") or version)
        except (OSError, json.JSONDecodeError):
            logger.debug("ignore invalid %s", pkg_meta_path)

    handler = resolve_handler(skill_key)
    output_type = (meta.get("output_type") or "data").strip() or "data"
    if output_type not in ("data", "html"):
        output_type = "data"

    return {
        "skill_key": skill_key,
        "name": meta.get("name") or skill_key,
        "description": description[:512],
        "version": version,
        "content": compact_content(body) or f"Local skill package: {base}",
        "bos_path": f"local://{base}",       # 复用 bos_path 列记本地路径，不新增列
        "status": "enabled" if handler else "failed",
        "output_type": output_type,
        "meta": {
            "handler": str(handler) if handler else "",
            "keywords": _split_keywords(meta, description, skill_key),
            "requires_link": str(meta.get("requires_link") or "").lower() in ("true", "yes", "1"),
            "local_path": str(base),
        },
    }


def load_all_packages() -> list[dict]:
    """扫描并解析全部本地包，解析失败的跳过。"""
    result = []
    for key in list_local_packages():
        pkg = load_package(key)
        if pkg:
            result.append(pkg)
    return result