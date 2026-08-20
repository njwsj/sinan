# sinan/services/generation_runner.py
import asyncio
import json
import logging
from pathlib import Path

from sinan.agents.llm import LLMClient
from sinan.agents.graph import build_graph
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep
from sinan.models.enums import SessionStatus, PageStatus
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus
from sinan.config.settings import settings
from sinan.services.page_store import page_store
import uuid
import socket
from contextlib import suppress
from sinan.services.generation_job_store import generation_job_store, CANCELLED
from sinan.services import cancel_registry
from sinan.models import events
from sinan.models.enums import PipelineState

_OWNER = f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"
_LEASE_SECONDS = 90
_HEARTBEAT_SECONDS = 20

logger = logging.getLogger(__name__)


class GenerationRunner:

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.graph = build_graph(llm)

    async def _execute_generation_pipeline(self, job) -> None:
        """
        后台异步执行生成流程。
        由 generate 路由通过 asyncio.create_task 启动，不阻塞请求。

        attachments: 前端传来的附件元数据列表（来自 /api/v1/data/upload 响应）。
                     Runner 从本地文件加载完整数据（hydrate），作为结构化数据传入
                     LangGraph state["attachments"]，由各 agent 按需读取。
        """
        payload = dict(job.request_payload or {})
        session_id = job.session_id
        marker = job.marker or f"page_{session_id[:8]}"
        attachments = payload.get("attachments") or []

        resolved_marker = marker or f"page_{session_id[:8]}"
        await session_store.update(
            session_id,
            status=SessionStatus.ACTIVE.value,
            pipeline_state=PipelineState.INIT.value,
        )
        await cancel_registry.clear_async(session_id)

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
                "router": "正在识别需求意图...",
                "analyst": "正在分析需求...",
                "designer": "正在制定设计方案...",
                "coder": "AI 正在生成页面代码...",
                "verifier": "正在验证页面...",
                "fixer": "正在修复问题...",
            }
            final_state = None
            async for event in self.graph.astream_events(
                    {
                        "session_id": session_id,
                        "job_id": job.job_id,
                        "marker": resolved_marker,
                        "user_id": session.user_id if session else "system",
                        "user_input": prompt,
                        "attachments": hydrated,
                        "datasources": payload.get("datasources") or [],
                        "template_id": payload.get("template_id"),
                        "fix_round": 0,
                        "max_fix_rounds": settings.max_fix_rounds,
                        "gate_reports": [],
                        "contract_errors": [],
                        "fix_history": [],
                        "pipeline_state": PipelineState.INIT.value,
                        "status": "routing",
                    },
                    config={"configurable": {"thread_id": session_id}},
                    version="v2",
            ):
                # —— 运行中取消检测（节点边界，跨实例） ——
                if await cancel_registry.is_cancelled_async(session_id):
                    await generation_job_store.request_cancel(job_id=job.job_id)
                    # 参考项目没有 cancelled 会话态（取消由 error 事件承载），
                    # 这里落 failed + error_message，作为未对齐项记录在 state-matrix。
                    await session_store.update(
                        session_id,
                        status=SessionStatus.FAILED.value,
                        pipeline_state=PipelineState.FAILED.value,
                        error_message="cancelled by user",
                    )
                    await event_bus.publish(
                        session_id, events.CANCELLED, events.cancelled_data(),
                        job_id=job.job_id, marker=resolved_marker,
                    )
                    return  # 正常返回，run_job 复查到 cancelled 不置 completed
                kind = event["event"]
                name = event.get("name", "")

                # 节点开始时推进度事件
                if kind == "on_chain_start":
                    node_name = event.get("metadata", {}).get("langgraph_node", "")
                    if node_name in step_labels:
                        await event_bus.publish(
                            session_id, events.STEP,
                            events.step_data(node_name, step_labels[node_name], node_name),
                            job_id=job.job_id, marker=resolved_marker,
                        )
                        await self._write_step(session_id, node_name, f"开始{node_name}")

                # 节点结束：只用于捕获整图完成后的最终 state
                elif kind == "on_chain_end":
                    # 图执行结束后拿到最终 state
                    if event.get("run_id") and name == "LangGraph":
                        final_state = event["data"].get("output")

            # fix_start / fix_applied 现在由 fixer 节点内部按轮发布，
            # runner 不再事后补发，否则同一轮会出现两条 fix_applied。
            fix_round = final_state.get("fix_round", 0)
            verification = final_state.get("verification_result") or {}
            quality_score = float(verification.get("quality_score") or 0.0)
            issues = verification.get("issues") or []

            # 低置信度挂起：图在 analyst 之后就 END 了，没有 code
            if final_state.get("status") == "awaiting_confirmation":
                await session_store.update(
                    session_id,
                    status=SessionStatus.PAUSED.value,
                    # sinan 增量：参考 analyst 只写 analysis，session 级 user_confirm 是本项目扩展
                    pipeline_state=PipelineState.USER_CONFIRM.value,
                    requirement_doc=final_state.get("requirement_doc") or "",
                )
                await event_bus.publish(
                    session_id, events.AWAITING_CONFIRMATION,
                    {
                        "message": "需求信息不足，请确认后继续",
                        "confirmation_digest": (final_state.get("analysis_output") or {})
                            .get("confirmation_digest", ""),
                        "requirement_doc": final_state.get("requirement_doc") or "",
                    },
                    job_id=job.job_id, marker=resolved_marker,
                )
                await generation_job_store.mark_waiting(job.job_id, _OWNER)
                return   # Job 落 waiting，等 Step 8 的确认接口恢复

            verify_message = (
                "校验通过" if verification.get("passed")
                else "；".join(str(i.get("description", "")) for i in issues[:5]) or "校验未通过"
            )
            await event_bus.publish(
                session_id, events.VERIFY_RESULT,
                {
                    **events.verify_result_data(
                        passed=bool(verification.get("passed")),
                        quality_score=quality_score,
                        issues=issues,
                        round_num=fix_round,
                    ),
                    "message": verify_message,
                },
                job_id=job.job_id, marker=resolved_marker,
            )

            if not verification.get("passed"):
                raise ValueError(f"验证失败（已修复 {fix_round} 轮）：{verify_message}")

            html = final_state["code"]

        except Exception as e:
            """
            注意：原 start() 内部 except 里对 session 的 FAILED 终态写入建议去掉（保留推 error 事件即可），
            让终态统一由 run_job 决定。异常直接抛出交给 run_job 接住。
            """
            logger.exception("generation failed for session %s", session_id)
            await event_bus.publish(
                session_id, events.ERROR, events.error_data(f"生成失败：{e}"),
                job_id=job.job_id, marker=resolved_marker,
            )
            return

        # 托管：写 page_version 表，更新 session
        marker = resolved_marker
        version = await page_store.next_version(marker)
        await page_store.save(
            marker=marker,
            version=version,
            html=html,
            created_by=session.user_id if session else "system",
            session_id=session_id,
            title=(session.prompt if session else "")[:128],
            harness_score=quality_score,
            repair_rounds=fix_round,
        )
        # 拼预览 URL（本地开发用 /page/{marker}，生产替换域名）
        preview_url = f"/api/page/preview/{marker}"
        # 更新 session：状态 DONE + marker + version + preview_url
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED.value,
            pipeline_state=PipelineState.DELIVERED.value,
            marker=marker,
            version=version,
            preview_url=preview_url,
            fix_rounds=fix_round,
            verification_score=quality_score,
        )

        # 推送托管完成事件，再关闭 SSE 流
        await event_bus.publish(
            session_id, events.COMPLETED,
            events.completed_data(
                version=version,
                preview_url=preview_url,
                quality_score=quality_score,
            ),
            job_id=job.job_id, marker=marker,
        )

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



    async def run_job(self, job_id: str) -> None:
        """领取并执行一个 Job：抢租约 → 心跳续租 → 执行流水线 → finalize。"""

        """
        因为同一个 Job 可能被多个执行者同时看到并想跑
        多实例部署：sinan 起了 3 个进程（或 3 个 pod）。它们的 supervisor 都在每 15s 扫 list_reclaimable_jobs()。同一个 pending Job，很可能被 3 个进程同时扫到，3 个都想 run_job。
        """
        job = await generation_job_store.claim_job(job_id, _OWNER, _LEASE_SECONDS)
        if not job:
            return  # 没抢到（已被别人持有 / 终态 / 达上限）
        """
        光抢到租约还不够，因为抢到的 worker 也可能中途挂掉（进程崩溃、OOM、机器宕机、网络断）。这时候问题来了：
        别的 worker 怎么知道"这个 running 的 Job 是还在跑，还是持有者已经死了"?
        答案就是租约的"到期时间"lease_until。约定：只要我还活着、还在跑这个 Job，
        我就周期性地把 lease_until 往后推——这就是心跳
        （_heartbeat_loop 每 20s 调一次 heartbeat，把 lease_until 续到 now+90s）。
        """
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id))
        try:
            await self._execute_generation_pipeline(job)
            latest = await generation_job_store.get_job(job_id)   # finalize 前复查
            if latest and latest.status == CANCELLED:
                return                                            # 被取消：不置 completed
            await generation_job_store.mark_completed(job_id, _OWNER)
        except asyncio.CancelledError:
            raise                                                 # 关机取消：交给下次恢复，不置 failed
        except Exception as e:
            logger.exception("generation job failed: job_id=%s", job_id)
            # 失败：置 failed，supervisor_loop 主要是针对进程崩溃这种情况，干净异常失败（LLM 报错、验证抛异常）因为这类失败重跑大概率还是同样结果，自动重试没意义，交给用户重新发起。
            await generation_job_store.mark_failed(job_id, _OWNER, str(e) or type(e).__name__)
            await session_store.update(
                job.session_id,
                status=SessionStatus.FAILED.value,
                pipeline_state=PipelineState.FAILED.value,
                error_message=str(e) or type(e).__name__,
            )
        finally:
            # 确保心跳任务被取消，避免僵尸任务
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task

    async def _heartbeat_loop(self, job_id: str) -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_SECONDS)
            ok = await generation_job_store.heartbeat(job_id, _OWNER, _LEASE_SECONDS)
            if not ok:
                logger.warning("heartbeat lost ownership: job_id=%s", job_id)
                return


# 模块级单例：用 settings 里的配置初始化 LLM 和 CoderAgent
_llm = LLMClient(
    api_key=settings.llm_api_key,
    model=settings.llm_model,
    base_url=settings.llm_base_url,
)
generation_runner = GenerationRunner(_llm)