# sinan/services/generation_runner.py
import asyncio
import json
import logging
from pathlib import Path

from sinan.agents.llm import LLMClient
from sinan.agents.graph import build_graph
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep, PageVersion
from sinan.models.enums import SessionStatus, PageStatus
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus
from sinan.config.settings import settings
from sinan.services.page_store import page_store

logger = logging.getLogger(__name__)


class GenerationRunner:

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.graph = build_graph(llm)

    async def start(self, session_id: str, attachments: list[dict] | None = None) -> None:
        """
        后台异步执行生成流程。
        由 generate 路由通过 asyncio.create_task 启动，不阻塞请求。

        attachments: 前端传来的附件元数据列表（来自 /api/v1/data/upload 响应）。
                     Runner 从本地文件加载完整数据（hydrate），作为结构化数据传入
                     LangGraph state["attachments"]，由各 agent 按需读取。
        """
        await session_store.update(session_id, status=SessionStatus.RUNNING)

        try:
            session = await session_store.get(session_id)
            prompt = session.prompt if session else ""

            # hydrate：从本地 JSON 文件加载 Excel 完整数据，填入 parsed 字段
            # parsed 结构：{"columns": [...], "rows": [...全量，不截断...], "row_count": int}
            hydrated: list[dict] = []
            for att in (attachments or []):
                file_id = att.get("file_id", "")
                json_path = Path(settings.attachment_storage_path) / f"{file_id}.json"
                if json_path.exists():
                    parsed = json.loads(json_path.read_text(encoding="utf-8"))
                    hydrated.append({**att, "parsed": parsed})
                    logger.info("hydrated attachment: file_id=%s rows=%d", file_id, parsed.get("row_count", 0))
                else:
                    logger.warning("attachment file not found, skipping: file_id=%s", file_id)
                    hydrated.append(att)


            # 执行 LangGraph 图（内部串行执行 analyze → design → code → verify）
            # attachments 作为结构化数据传入 state，由 analyzer/coder 各自按需读取

            step_labels = {
                "analyze": "正在分析需求...",
                "design": "正在制定设计方案...",
                "code": "AI 正在生成页面代码...",
                "fix": "正在修复问题...",
                "verify": "正在验证页面...",
            }
            final_state = None
            async for event in self.graph.astream_events(
                    {
                        "prompt": prompt,
                        "attachments": hydrated,
                        "iteration": 0,
                        "max_iterations": 3,
                        "session_id": session_id,  # 新增
                        "marker": f"page_{session_id[:8]}",  # 新增
                        "user_id": session.user_id if session else "system",  # 新增
                    },
                    # 这个config参数必须要传，每个 session_id 对应一个独立的 LangGraph thread，它们的 checkpoint 数据互不干扰，但底层都共享同一个进程和事件循环。
                    config={"configurable": {"thread_id": session_id}},
                    version="v2",
            ):
                kind = event["event"]
                name = event.get("name", "")

                # 节点开始时推进度事件
                if kind == "on_chain_start":
                    node_name = event.get("metadata", {}).get("langgraph_node", "")
                    if node_name in step_labels:
                        await event_bus.publish(session_id, node_name, {"message": step_labels[node_name]})
                        await self._write_step(session_id, node_name, f"开始{node_name}")

                # 图执行结束后拿到最终 state
                elif kind == "on_chain_end" and event.get("run_id") and name == "LangGraph":
                    final_state = event["data"].get("output")

            # 如果经历了修复，推送修复事件
            if final_state.get("iteration", 0) > 0:
                await event_bus.publish(
                    session_id,
                    "fix",
                    {"message": f"经过 {final_state['iteration']} 轮修复"},
                )
                await self._write_step(
                    session_id, "fix",
                    f"修复完成，共 {final_state['iteration']} 轮",
                )

                # 推送验证结果
                await self._write_step(session_id, "verify", final_state.get("verify_message", ""))
                await event_bus.publish(
                    session_id, "verify",
                    {"message": final_state.get("verify_message", "校验完成")},
                )

            if not final_state.get("verified"):
                raise ValueError(
                    f"验证失败（已修复 {final_state.get('iteration', 0)} 轮）："
                    f"{final_state.get('verify_message', '未知错误')}"
                )

            html = final_state["html"]

        except Exception as e:
            logger.exception("generation failed for session %s", session_id)
            await event_bus.publish(session_id, "error", {"message": f"生成失败：{e}"})
            await session_store.update(session_id, status=SessionStatus.FAILED)
            await event_bus.publish_done(session_id)
            return

        # 托管：写 page_version 表，更新 session
        marker = f"page_{session_id[:8]}"
        version = await page_store.next_version(marker)
        await page_store.save(
            marker=marker,
            version=version,
            html=html,
            created_by=session.user_id if session else "system",
        )
        # 拼预览 URL（本地开发用 /page/{marker}，生产替换域名）
        preview_url = f"/api/v1/page/{marker}"
        # 更新 session：状态 DONE + marker + version + preview_url
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED,
            marker=marker,
            version=version,
            preview_url=preview_url,
        )

        # 推送托管完成事件，再关闭 SSE 流
        await event_bus.publish(session_id, "done", {
            "message": "页面生成完成",
            "preview_url": preview_url,
            "marker": marker,
            "version": version,
        })
        await event_bus.publish_done(session_id)

    async def _write_step(self, session_id: str, step: str, message: str) -> None:
        """把步骤执行记录写入 gen_session_step 表"""
        record = GenSessionStep(
            session_id=session_id,
            step=step,
            direction="output",
            output_data={"message": message},
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()

    async def _save_page(self, marker: str, version: int, html: str, created_by: str) -> None:
        """把生成的 HTML 存入 page_version 表"""
        record = PageVersion(
            marker=marker,
            version=version,
            html_content=html,
            status=PageStatus.PUBLISHED,
            created_by=created_by,
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()


# 模块级单例：用 settings 里的配置初始化 LLM 和 CoderAgent
_llm = LLMClient(
    api_key=settings.llm_api_key,
    model=settings.llm_model,
    base_url=settings.llm_base_url,
)
generation_runner = GenerationRunner(_llm)