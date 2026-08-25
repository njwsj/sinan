# sinan/agents/skill_agent.py
"""Skill 节点：在 analyst 之前完成外部知识准备。

对齐参考 page/claude_code/codegen_engine.py 的 preprocess_skill：
  选 Skill → 缺链接则挂起 → 摄取知识库 → 逐个执行 Skill → 结果写回 state。

放在 router 之后、analyst 之前，因为 analyst/coder 都要读 external_knowledge
（参考 page/agents/analyst.py:183 也是从 state 里取 external_knowledge / skill_result）。

本节点不套 harness/wrap_node：它不产出受契约约束的业务文档，
门禁分派表里也没有对应的门（与 fixer 同样处理）。
"""
from __future__ import annotations

import json
import logging

from sinan.agents.state import GenerationState
from sinan.config.settings import settings
from sinan.models import events
from sinan.runtime.tool_registry import tool_registry
from sinan.services.artifact_store import artifact_store
from sinan.services.generation_event_bus import event_bus
from sinan.services.knowledge_context import load_knowledge_sources

logger = logging.getLogger(__name__)


class SkillAgent:
    """Skill 与知识库预处理节点。"""

    def __init__(self, llm=None):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        session_id = state.get("session_id", "")
        marker = state.get("marker")
        prompt = state.get("user_input", "")
        skill_keys = list(state.get("skill_keys") or [])
        knowledge_sources = list(state.get("knowledge_sources") or [])

        # confirm / iterate 续跑时若已加载过，直接跳过，避免重复抓取与重复计费
        if state.get("external_knowledge_loaded"):
            logger.info("skill node skipped: knowledge already loaded, session=%s", session_id)
            return {}

        # ---- 1. 选 Skill ----
        try:
            selected = await tool_registry.select(prompt, skill_keys, llm=self.llm)
        except Exception:
            logger.exception("skill selection failed, continue without skill")
            selected = []

        # ---- 2. 缺链接 → 挂起（图在本节点后 END）----
        # 只在首轮生成时拦截：confirm / iterate 路径 user_confirmed=True，
        # 说明用户已经明确表示"就这样继续"，此时再拦会陷入
        # 「挂起 → 用户确认但没给链接 → 再挂起」的死循环。
        link_hint = "" if state.get("user_confirmed") else tool_registry.needs_link(
            prompt, selected, knowledge_sources
        )
        if link_hint:
            if session_id:
                await event_bus.publish(
                    session_id, events.SKILL_LINK_REQUIRED,
                    events.skill_link_required_data(
                        link_hint, [s["skill_key"] for s in selected]
                    ),
                    marker=marker,
                )
            return {
                "selected_skills": selected,
                "skill_link_required": True,
                "status": "awaiting_confirmation",
                "requirement_doc": link_hint,
            }

        # ---- 3. 摄取知识库 ----
        knowledge = {"items": [], "text": "", "ok_count": 0, "chars": 0}
        if knowledge_sources:
            knowledge = await load_knowledge_sources(
                knowledge_sources, session_id=session_id, marker=marker
            )

        # ---- 4. 执行 Skill ----
        results: list[dict] = []
        if selected:
            if session_id:
                await event_bus.publish(
                    session_id, events.SKILL_RUNNING,
                    events.skill_running_data(
                        [s["skill_key"] for s in selected],
                        explicit=bool(skill_keys),
                    ),
                    marker=marker,
                )
            for skill in selected:      # 串行执行，保证事件顺序稳定、便于双项目对照
                result = await tool_registry.execute(
                    skill, prompt=prompt, session_id=session_id, marker=marker or ""
                )
                results.append(result)
                if session_id:
                    await event_bus.publish(
                        session_id, events.SKILL_RESULT,
                        events.skill_result_data(
                            result["skill_key"], result["name"], result["ok"],
                            result["content"], error=result["error"],
                            output_type=result["output_type"],
                            preview_limit=settings.skill_sse_preview_limit,
                        ),
                        marker=marker,
                    )
                if session_id and result["ok"]:
                    try:
                        await artifact_store.save_artifact(
                            session_id, f"skill_{result['skill_key']}"[:64],
                            {"_format": "text", "_content": result["content"],
                             "skill_key": result["skill_key"],
                             "output_type": result["output_type"]},
                            marker=marker,
                        )
                    except Exception:
                        logger.exception("save skill artifact failed: %s", result["skill_key"])

        # ---- 5. 合并成注入用的正文 ----
        ok_results = [r for r in results if r["ok"]]
        parts: list[str] = []
        if knowledge.get("text"):
            parts.append("## 知识库资料\n\n" + knowledge["text"])
        for r in ok_results:
            parts.append(f"## Skill 输出：{r['name']}（{r['skill_key']}）\n\n{r['content']}")
        external_knowledge = "\n\n".join(parts)

        failed = [{"skill_key": r["skill_key"], "error": r["error"]}
                  for r in results if not r["ok"]]
        if failed:
            logger.warning("skill failed but pipeline continues: %s",
                           json.dumps(failed, ensure_ascii=False))

        return {
            "selected_skills": selected,
            "skill_results": results,
            "skill_result": ok_results[-1]["content"] if ok_results else None,
            "skill_context": {
                "selected": [s["skill_key"] for s in selected],
                "ok_count": len(ok_results),
                "failed": failed,
            },
            "knowledge_context": knowledge,
            "external_knowledge": external_knowledge or None,
            "external_knowledge_loaded": True,
            "skill_link_required": False,
        }