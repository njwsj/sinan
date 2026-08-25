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
        from sinan.runtime.registry import RuntimeRegistry
        self._runtime_registry = RuntimeRegistry(self.graph)


    async def _build_state(self, job, session, *, action: str, body: dict) -> dict:
        marker = job.marker or f"page_{job.session_id[:8]}"
        hydrated = await self._hydrate_attachments(job.request_payload.get("attachments") or [])
        state = {
            "session_id": job.session_id,
            "job_id": job.job_id,
            "marker": marker,
            "user_id": session.user_id if session else "system",
            "user_input": session.prompt if session else "",
            "attachments": hydrated,
            "datasources": job.request_payload.get("datasources") or [],
            "template_id": job.request_payload.get("template_id"),
            # Step 12：Skill 与知识库入参
            "skill_keys": list(job.request_payload.get("skill_keys") or []),
            "knowledge_sources": list(job.request_payload.get("knowledge_sources") or []),
            "fix_round": 0,
            "max_fix_rounds": settings.max_fix_rounds,
            "gate_reports": [], "contract_errors": [], "fix_history": [],
            "pipeline_state": PipelineState.INIT.value,
            "status": "routing",
        }
        # Step 12：数据源取数（失败按 error_policy 处理，默认不阻断）
        if state["datasources"]:
            from sinan.services.data_service import data_service as _ds
            try:
                state["datasource_context"] = await _ds.resolve_datasources(state["datasources"])
            except Exception as e:
                logger.warning("resolve datasources failed: %s", e)
                state["datasource_context"] = {"items": [], "ok_count": 0, "error": str(e)}

        if action in ("confirm", "iterate"):
            # 关键：iteration_feedback 非空 → analyzer.parse_analyst_response 不再挂起，
            #       直接 user_confirmed=True 放行到 designer（analyzer.py:160）
            state["iteration_feedback"] = body.get("feedback") or "(用户已确认，继续生成)"
            state["user_confirmed"] = True
            # Step 12：用户在确认/迭代时补充的链接与 Skill 合并进 state，
            # 供 skill 节点重新执行（此时 external_knowledge_loaded 未置位，会真正加载）
            extra_links = [*(body.get("knowledge_sources") or [])]
            if body.get("link"):
                extra_links.append(body["link"])
            if extra_links:
                state["knowledge_sources"] = [
                    *state["knowledge_sources"],
                    *[l for l in extra_links if l not in state["knowledge_sources"]],
                ]
            if body.get("skill_keys"):
                state["skill_keys"] = list(body["skill_keys"])
            # 迭代时把当前页面代码带进 state，供 analyst/designer 参考（analyzer.py:137 已支持）
            current = await page_store.get(marker)
            if current:
                state["code"] = current.html_content
        return state

    async def _run_confirm(self, job) -> None:
        body = (job.request_payload or {}).get("body") or {}
        session = await session_store.get(job.session_id)
        marker = job.marker or f"page_{job.session_id[:8]}"

        if not body.get("confirmed", True):
            # 拒绝：保留 paused，记录反馈，发 awaiting_confirmation(rejected)
            await session_store.update(
                job.session_id,
                status=SessionStatus.PAUSED.value,
                pipeline_state=PipelineState.USER_CONFIRM.value,
            )
            await event_bus.publish(
                job.session_id, events.AWAITING_CONFIRMATION,
                {"message": "已收到您的反馈，请补充需求后重新确认",
                 "rejected": True, "feedback": body.get("feedback") or ""},
                job_id=job.job_id, marker=marker,
            )
            return

        state = await self._build_state(job, session, action="confirm", body=body)
        await self._run_graph(job, state, session)


    async def _run_iterate(self, job) -> None:
        from sinan.agents.direct_editor import direct_editor, session_edit_locks, DIRECT_EDIT_PRECHECK
        from sinan.harness.iteration_router import classify_iteration, apply_text_replacements

        body = (job.request_payload or {}).get("body") or {}
        feedback = body.get("feedback") or ""
        session = await session_store.get(job.session_id)
        marker = job.marker or f"page_{job.session_id[:8]}"
        current = await page_store.get(marker)
        if current is None:
            await event_bus.publish(job.session_id, events.ERROR,
                                    events.error_data("当前会话还没有已生成页面，无法迭代"),
                                    job_id=job.job_id, marker=marker)
            return
        html = current.html_content

        # 1) 直接编辑快路径（形如 修改「#id」: ...）
        if DIRECT_EDIT_PRECHECK.match(feedback.strip()):
            async with session_edit_locks.lock_for(job.session_id):
                modified, source = direct_editor.try_edit(feedback, html)
            if source == "direct_edit" and modified:
                await self._save_iteration_version(job, session, marker, modified,
                                                   note="direct_edit", extra={"direct_edit": True})
                return
            # 未命中则继续走分类

        # 2) 分类
        decision = await classify_iteration(
            feedback, {"session_id": job.session_id, "marker": marker},
            history=(session.messages or []) if session else None,
            llm=self.llm,
        )

        # 3) 纯文本替换
        if decision.get("change_scope") == "text_replace":
            modified, applied = apply_text_replacements(html, decision["replacements"])
            if applied:
                await self._save_iteration_version(job, session, marker, modified,
                                                   note="text_replace")
                return

        # 4) structural/partial → 重跑图（iteration_feedback 已在 _build_state 注入）
        state = await self._build_state(job, session, action="iterate", body=body)
        # 可选：把 decision.target_step 记进 state 供 designer/coder 决定改动范围
        state["iteration_route"] = decision
        await self._run_graph(job, state, session)

    async def _save_iteration_version(self, job, session, marker, html, *, note="", extra=None):
        version = await page_store.next_version(marker)
        await page_store.save(marker=marker, version=version, html=html,
                              created_by=session.user_id if session else "system",
                              session_id=job.session_id,
                              title=(session.prompt if session else "")[:128], note=note)
        preview_url = f"/api/page/preview/{marker}"
        await session_store.update(job.session_id,
                                   status=SessionStatus.COMPLETED.value,
                                   pipeline_state=PipelineState.DELIVERED.value,
                                   marker=marker, version=version, preview_url=preview_url)
        data = events.completed_data(version=version, preview_url=preview_url, quality_score=0.0)
        if extra:
            data.update(extra)
        await event_bus.publish(job.session_id, events.COMPLETED, data,
                                job_id=job.job_id, marker=marker)


    async def _run_graph(self, job, initial_state: dict, session) -> None:
        """通过 RuntimeRegistry 路由到对应 Runtime，消费 RuntimeEvent → SSE。

        generate / confirm / iterate 三条路径共用，差异只体现在传入的 initial_state。
        """
        session_id = job.session_id
        resolved_marker = initial_state.get("marker") or f"page_{session_id[:8]}"
        mode = (job.request_payload or {}).get("mode") or "native"
        runtime = self._runtime_registry.get(mode)

        try:
            final_state: dict | None = None

            async for rt_event in runtime.run_generation(
                initial_state, thread_id=session_id
            ):
                # —— 取消检测（节点边界） ——
                if await cancel_registry.is_cancelled_async(session_id):
                    await generation_job_store.request_cancel(job_id=job.job_id)
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
                    return

                # —— RuntimeEvent → SSEEvent ——
                if rt_event.type == "step":
                    node_name = rt_event.data.get("agent") or rt_event.data.get("step", "")
                    await event_bus.publish(
                        session_id, events.STEP,
                        events.step_data(
                            node_name,
                            rt_event.data.get("message", ""),
                            node_name,
                        ),
                        job_id=job.job_id, marker=resolved_marker,
                    )
                    await self._write_step(session_id, node_name,
                                           rt_event.data.get("message", f"开始{node_name}"))

                elif rt_event.type == "graph_output":
                    final_state = rt_event.data

            if final_state is None:
                raise ValueError("Runtime 未产生 graph_output 事件，生成流程异常终止")

            fix_round = final_state.get("fix_round", 0)
            verification = final_state.get("verification_result") or {}
            quality_score = float(verification.get("quality_score") or 0.0)
            issues = verification.get("issues") or []

            # 低置信度挂起
            if final_state.get("status") == "awaiting_confirmation":
                link_required = bool(final_state.get("skill_link_required"))
                await session_store.update(
                    session_id,
                    status=SessionStatus.PAUSED.value,
                    pipeline_state=PipelineState.USER_CONFIRM.value,
                    requirement_doc=final_state.get("requirement_doc") or "",
                )
                if link_required:
                    payload = {
                        "message": final_state.get("requirement_doc")
                                   or "请补充知识库链接后确认继续",
                        "link_required": True,
                        "skill_keys": [s.get("skill_key") for s in
                                       (final_state.get("selected_skills") or [])],
                        "requirement_doc": "",
                        "confirmation_digest": "",
                    }
                else:
                    payload = {
                        "message": "需求信息不足，请确认后继续",
                        "confirmation_digest": (final_state.get("analysis_output") or {})
                        .get("confirmation_digest", ""),
                        "requirement_doc": final_state.get("requirement_doc") or "",
                    }
                await event_bus.publish(
                    session_id, events.AWAITING_CONFIRMATION, payload,
                    job_id=job.job_id, marker=resolved_marker,
                )
                await generation_job_store.mark_waiting(job.job_id, _OWNER)
                return

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
            logger.exception("generation failed for session %s", session_id)
            await event_bus.publish(
                session_id, events.ERROR, events.error_data(f"生成失败：{e}"),
                job_id=job.job_id, marker=resolved_marker,
            )
            return

        # 落版本
        version = await page_store.next_version(resolved_marker)
        await page_store.save(
            marker=resolved_marker,
            version=version,
            html=html,
            created_by=session.user_id if session else "system",
            session_id=session_id,
            title=(session.prompt if session else "")[:128],
            harness_score=quality_score,
            repair_rounds=fix_round,
        )
        preview_url = f"/api/page/preview/{resolved_marker}"
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED.value,
            pipeline_state=PipelineState.DELIVERED.value,
            marker=resolved_marker,
            version=version,
            preview_url=preview_url,
            fix_rounds=fix_round,
            verification_score=quality_score,
        )
        await event_bus.publish(
            session_id, events.COMPLETED,
            events.completed_data(
                version=version,
                preview_url=preview_url,
                quality_score=quality_score,
            ),
            job_id=job.job_id, marker=resolved_marker,
        )

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

        session = await session_store.get(session_id)
        initial_state = await self._build_state(job, session, action="generate", body={})
        # ── 模板代码加载（集中在此处，对齐参考 generate.py:639-645）──
        # prompt_template_id 优先：取源页面代码作为模板基准
        prompt_template_id = payload.get("prompt_template_id")
        template_id = payload.get("template_id")
        if prompt_template_id:
            from sinan.services.template_store import template_store as _ts
            tmpl = await _ts.resolve_prompt_template(prompt_template_id)
            if tmpl and tmpl.template_id:  # template_id 字段存的是源页面 marker
                source_page = await page_store.get(tmpl.template_id)
                if source_page and source_page.html_content:
                    initial_state["template_code"] = source_page.html_content
                    logger.info(
                        "prompt_template branch: id=%s source_marker=%s session=%s",
                        prompt_template_id, tmpl.template_id, session_id,
                    )
                else:
                    logger.warning("prompt_template source page not found: id=%s", prompt_template_id)
        elif template_id:
            from sinan.services.template_store import template_store as _ts
            template_code = await _ts.download_html_template(template_id)
            if template_code:
                initial_state["template_code"] = template_code
            else:
                logger.warning("template_id not found or unreadable: %s", template_id)
        await self._run_graph(job, initial_state, session)

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

    async def _hydrate_attachments(self, attachments: list) -> list[dict]:
        """加载附件解析数据，优先从 attachment 表 + LocalStorage 读取，旧路径兜底。

        优先级：
        1. attachment 表有 meta.storage_uri → 从 LocalStorage 读解析 JSON
        2. 旧路径兜底：settings.attachment_storage_path/{file_id}.json
        3. 都没有 → 原样返回，不阻断流水线
        """
        from sinan.services.storage import storage as _storage

        hydrated: list[dict] = []
        for att in (attachments or []):
            file_id = att.get("file_id") or ""
            if not file_id:
                hydrated.append(att)
                continue

            parsed = None

            # —— 方式 1：attachment 表 + LocalStorage ——
            try:
                record = await session_store.get_attachment(file_id)
                if record and record.meta:
                    uri = record.meta.get("storage_uri") or ""
                    if uri:
                        key = uri.removeprefix("local://")
                        raw = await _storage.get(key)
                        parsed = json.loads(raw.decode("utf-8"))
            except Exception as e:
                logger.debug("attachment 表读取失败 file_id=%s: %s，尝试旧路径", file_id, e)

            # —— 方式 2：旧本地文件兜底 ——
            if parsed is None:
                json_path = Path(settings.attachment_storage_path) / f"{file_id}.json"
                if json_path.exists():
                    parsed = json.loads(json_path.read_text(encoding="utf-8"))
                    logger.info("attachment 用旧路径加载: file_id=%s", file_id)

            if parsed is not None:
                hydrated.append({**att, "parsed": parsed})
                logger.info(
                    "hydrated attachment: file_id=%s rows=%d",
                    file_id, parsed.get("row_count", 0),
                )
            else:
                logger.warning("attachment 无法加载，原样传入: file_id=%s", file_id)
                hydrated.append(att)

        return hydrated



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
            action = (job.request_payload or {}).get("action", "generate")
            if action == "confirm":
                await self._run_confirm(job)
            elif action == "iterate":
                await self._run_iterate(job)
            else:
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