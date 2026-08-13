# sinan/services/generation_runner.py
import asyncio
import logging

from sinan.agents.coder import CoderAgent
from sinan.agents.graph import build_graph
from sinan.agents.llm import LLMClient
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep, PageVersion
from sinan.models.enums import SessionStatus, PageStatus
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus
from sinan.config.settings import settings

logger = logging.getLogger(__name__)


class GenerationRunner:


    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.graph = build_graph(llm)

    async def start(self, session_id: str) -> None:
        """
        后台异步执行生成流程。
        由 generate 路由通过 asyncio.create_task 启动，不阻塞请求。
        """
        await session_store.update(session_id, status=SessionStatus.RUNNING)

        try:
            session = await session_store.get(session_id)
            prompt = session.prompt if session else ""

            # 步骤事件：analyze
            await event_bus.publish(session_id, "analyze", {"message": "正在分析需求..."})
            await self._write_step(session_id, "analyze", "开始需求分析")

            # 步骤事件：design
            await event_bus.publish(session_id, "design", {"message": "正在制定设计方案..."})
            await self._write_step(session_id, "design", "开始设计")

            # 步骤事件：code
            await event_bus.publish(session_id, "code", {"message": "AI 正在生成页面代码..."})
            await self._write_step(session_id, "code", "开始生成")

            # 执行 LangGraph 图（内部串行执行 analyze → design → code → verify）
            final_state = await self.graph.ainvoke({"prompt": prompt})

            await self._write_step(session_id, "verify", final_state["verify_message"])
            await event_bus.publish(
                session_id, "verify", {"message": final_state["verify_message"]}
            )

            if not final_state["verified"]:
                raise ValueError(final_state["verify_message"])

            html = final_state["html"]

        except Exception as e:
            logger.exception("generation failed for session %s", session_id)
            await event_bus.publish(session_id, "error", {"message": f"生成失败：{e}"})
            await session_store.update(session_id, status=SessionStatus.FAILED)
            await event_bus.publish_done(session_id)
            return

        # 托管：写 page_version 表，更新 session
        marker = f"page_{session_id[:8]}"
        version = 1
        await self._save_page(marker, version, html, created_by=session_id)
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED,
            marker=marker,
            version=version,
            preview_url=f"/api/v1/page/{marker}",
        )

        # 推送托管完成事件，再关闭 SSE 流
        await event_bus.publish(
            session_id,
            "host",
            {"message": f"页面已生成，预览地址: /api/v1/page/{marker}", "url": f"/api/v1/page/{marker}"},
        )
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