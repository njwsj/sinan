# sinan/runtime/tool_registry.py
"""运行时工具（Skill）注册表：选择 → 执行 → 归一化。

承担计划 12.2 的六项职责：
  列出可用 Skill / 按场景过滤 / 解析显式 skill_keys / 按 Prompt 路由 / 执行 / 归一化输出。

对齐参考 page/claude_code/codegen_engine.py 的 preprocess_skill + skill_executor：
  - 显式 skill_keys 优先，且「显式指定但库里没有」时仍造一条占位记录（参考同样行为）；
  - 显式为空时才走路由；
  - 执行走子进程，超时用 asyncio.wait_for，输出做截断；
  - 结果统一成 {skill_key, name, ok, content, error, output_type, debug}。

有意的差异：
  - 参考的 auto 路由在代码里被硬关掉（selected = []），sinan 打开关键词路由，
    否则「Prompt 能路由到匹配 Skill」这条验收标准无法验证；
  - 不注入任何凭证环境变量（参考注入 UGATE_TOKEN / PL_API_*）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from sinan.config.settings import settings
from sinan.services import skill_package
from sinan.services.skill_registry import skill_registry

logger = logging.getLogger(__name__)

_LINK_HINT_WORDS = ("知识库", "ku.baidu-int.com", "wiki", "文档链接", "这个文档", "该文档")


class ToolRegistry:
    """Skill 的运行时视图。无状态，可安全做成模块级单例。"""

    # ---------- 列出与过滤 ----------

    async def list_available(self) -> list[dict]:
        """当前可用（enabled 且本地能找到 handler）的 Skill。"""
        available = []
        for skill in await skill_registry.list_enabled_skills():
            key = skill["skill_key"]
            try:
                handler = skill_package.resolve_handler(key)
            except ValueError:
                handler = None
            if handler is None:
                logger.warning("skill enabled but handler missing, skipped: %s", key)
                continue
            skill["_handler"] = str(handler)
            skill["_meta"] = (skill_package.load_package(key) or {}).get("meta", {})
            available.append(skill)
        return available

    def filter_by_scene(self, skills: list[dict], output_type: str | None = None) -> list[dict]:
        """按场景过滤。当前唯一场景维度是 output_type（data / html）。"""
        if not output_type:
            return skills
        return [s for s in skills if (s.get("output_type") or "data") == output_type]

    # ---------- 选择 ----------

    def resolve_explicit(self, skills: list[dict], skill_keys: list[str]) -> list[dict]:
        """解析显式 skill_keys。库里没有的 key 也保留占位记录（对齐参考行为）。"""
        wanted = [k for k in (skill_keys or []) if k]
        if not wanted:
            return []
        by_key = {s["skill_key"].lower(): s for s in skills}
        selected: list[dict] = []
        for key in wanted:
            hit = by_key.get(key.lower())
            if hit:
                selected.append({**hit, "_source": "explicit"})
            else:
                logger.info("explicit skill_key not installed, placeholder kept: %s", key)
                selected.append({"skill_key": key, "name": key, "description": "",
                                 "output_type": "data", "_handler": "", "_meta": {},
                                 "_source": "explicit_missing"})
        return selected

    def route_by_keywords(self, prompt: str, skills: list[dict]) -> list[dict]:
        """按 SKILL.md 的 keywords 做确定性路由，命中即选。零 LLM 调用。"""
        text = (prompt or "").lower()
        if not text:
            return []
        hits = []
        for skill in skills:
            keywords = (skill.get("_meta") or {}).get("keywords") or [skill["skill_key"]]
            matched = [k for k in keywords if k and k.lower() in text]
            if matched:
                hits.append({**skill, "_source": "routed", "_matched": matched})
        return hits

    async def route_by_llm(self, prompt: str, skills: list[dict], llm) -> list[dict]:
        """LLM 路由，默认关闭（settings.skill_route_by_llm）。Prompt 与参考一致。"""
        if not skills or llm is None:
            return []
        lines = "\n".join(
            json.dumps({"skill_key": s["skill_key"], "description": (s.get("description") or "")[:200]},
                       ensure_ascii=False)
            for s in skills[:20]
        )
        ask = (
            f"用户请求：{prompt}\n"
            f"可用 Skills，每行一个 JSON：\n{lines}\n"
            "判断是否需要调用 Skill，以及最适合调用哪些 Skill。\n"
            '只输出 JSON：{"use_skill": true/false, "skill_keys": ["skill_key"]}。'
        )
        try:
            raw = await llm.chat([{"role": "user", "content": ask}], temperature=0)
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except Exception as e:
            logger.warning("llm skill routing failed, fallback to keywords: %s", e)
            return []
        if not data.get("use_skill"):
            return []
        valid = {s["skill_key"] for s in skills}
        chosen = {str(k) for k in (data.get("skill_keys") or []) if str(k) in valid}
        return [{**s, "_source": "routed_llm"} for s in skills if s["skill_key"] in chosen]

    async def select(self, prompt: str, skill_keys: list[str], *, llm=None) -> list[dict]:
        """统一选择入口：显式优先，否则路由；都没命中返回空列表（不报错）。"""
        skills = await self.list_available()
        explicit = self.resolve_explicit(skills, skill_keys)
        if explicit:
            return explicit
        if settings.skill_route_by_llm:
            routed = await self.route_by_llm(prompt, skills, llm)
            if routed:
                return routed
        return self.route_by_keywords(prompt, skills)

    def needs_link(self, prompt: str, selected: list[dict],
                   knowledge_sources: list[str]) -> str:
        """判断是否必须让用户补链接。返回提示语，空串表示不需要。

        两种触发条件（第一条对齐参考 codegen_engine.py:511-529 的语义）：
          1. Prompt 里提到知识库/文档但没给任何链接，且没有 Skill 能兜住；
          2. 选中的 Skill 在 SKILL.md 里声明了 requires_link: true。
        """
        if knowledge_sources:
            return ""
        for skill in selected:
            if (skill.get("_meta") or {}).get("requires_link"):
                return f"Skill「{skill['skill_key']}」需要一个文档/知识库链接才能执行，请补充链接后确认继续。"
        text = (prompt or "").lower()
        if not selected and any(w.lower() in text for w in _LINK_HINT_WORDS):
            return "检测到你提到了知识库或文档，但没有提供链接。请补充链接后确认继续。"
        return ""

    # ---------- 执行 ----------

    async def execute(self, skill: dict, *, prompt: str, session_id: str,
                      marker: str, params: dict | None = None) -> dict:
        """执行一个 Skill 子进程，返回归一化结果。任何异常都转成 ok=False，不向上抛。"""
        skill_key = skill.get("skill_key") or ""
        handler = skill.get("_handler") or ""
        if not handler:
            return self.normalize(skill, ok=False, content="",
                                  error="handler not found（Skill 未安装或缺 handler.py）")

        payload = json.dumps({
            "prompt": prompt, "session_id": session_id,
            "marker": marker, "params": params or {},
        }, ensure_ascii=False).encode("utf-8")

        # 环境最小化：只透传 PATH / 语言相关变量，绝不透传凭证
        env = {k: v for k, v in os.environ.items()
               if k in ("PATH", "LANG", "LC_ALL", "PYTHONPATH", "HOME")}
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, handler,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(skill_package.skill_dir(skill_key)),
            )
        except Exception as e:
            return self.normalize(skill, ok=False, content="", error=f"spawn failed: {e}")

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(payload), timeout=settings.skill_timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            return self.normalize(skill, ok=False, content="",
                                  error=f"timeout after {settings.skill_timeout_seconds}s")

        out = (stdout or b"").decode("utf-8", errors="replace").strip()
        err = (stderr or b"").decode("utf-8", errors="replace").strip()
        debug = {"returncode": proc.returncode, "stdout_len": len(out), "stderr_len": len(err)}

        if proc.returncode != 0:
            return self.normalize(skill, ok=False, content=out,
                                  error=err or f"exit code {proc.returncode}", debug=debug)

        # 输出解析：优先按 JSON 协议，失败则整段 stdout 当纯文本结果（对齐参考的兜底策略）
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return self.normalize(skill, ok=bool(out), content=out,
                                  error="" if out else "empty output", debug=debug)

        if not isinstance(data, dict):
            return self.normalize(skill, ok=True, content=out, debug=debug)

        ok = bool(data.get("ok", True))
        content = data.get("content")
        content_str = (json.dumps(content, ensure_ascii=False)
                       if isinstance(content, (dict, list)) else str(content or ""))
        return self.normalize(skill, ok=ok, content=content_str,
                              error=str(data.get("error") or ""), debug=debug)

    def normalize(self, skill: dict, *, ok: bool, content: str,
                  error: str = "", debug: dict | None = None) -> dict:
        """统一 Skill 输出结构，并按 skill_output_limit 截断正文。"""
        limit = settings.skill_output_limit
        text = content or ""
        truncated = len(text) > limit
        if truncated:
            text = text[:limit] + "\n\n...(truncated)"
        return {
            "skill_key": skill.get("skill_key") or "",
            "name": skill.get("name") or skill.get("skill_key") or "",
            "ok": bool(ok),
            "content": text,
            "error": error or "",
            "output_type": skill.get("output_type") or "data",
            "source": skill.get("_source") or "",
            "truncated": truncated,
            "debug": debug or {},
        }


tool_registry = ToolRegistry()