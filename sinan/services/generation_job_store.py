# sinan/services/generation_job_store.py
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update, or_, and_, func

from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenerationJob

# Job 状态常量（字符串列，便于批量 UPDATE）
PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
TERMINAL_STATUSES = {COMPLETED, FAILED, CANCELLED}
ACTIVE_STATUSES = {PENDING, RUNNING}


@dataclass
class JobCreateResult:
    job: GenerationJob
    created: bool


def _new_job(payload: dict, session_id: str, marker: str, user_id: str) -> GenerationJob:
    """构造一个未入库的 Job；payload 里补齐 session_id/marker/user_id 以支持重放。"""
    now = datetime.now()
    payload = dict(payload or {})
    payload.update({"session_id": session_id, "marker": marker, "user_id": user_id})
    return GenerationJob(
        job_id=uuid.uuid4().hex,
        session_id=session_id,
        marker=marker,
        user_id=user_id,
        status=PENDING,
        request_payload=payload,
        attempts=0,
        max_attempts=3,
        created_at=now,
        updated_at=now,
    )

class GenerationJobStore:
    async def create_or_get_job(
        self, *, session_id: str, marker: str, user_id: str, payload: dict, reconnect: bool = False
    ) -> JobCreateResult:
        """同一 session 已有活动 Job（pending/running）则复用；否则新建。保证重复提交不产生两个活跃 Job。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenerationJob).where(GenerationJob.session_id == session_id)
                .order_by(GenerationJob.id.desc()).limit(1)
            )
            job = result.scalar_one_or_none()
            if job and job.status in ACTIVE_STATUSES:
                return JobCreateResult(job=job, created=False)
            if job and reconnect:
                return JobCreateResult(job=job, created=False)  # 重连复用最近一次 Job（含终态）
            job = _new_job(payload, session_id, marker, user_id)
            db.add(job)
            await db.commit()
            await db.refresh(job)
            return JobCreateResult(job=job, created=True)

    async def get_job(self, job_id: str) -> GenerationJob | None:
        """按 job_id 查询单个 Job，不存在时返回 None。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(GenerationJob).where(GenerationJob.job_id == job_id))
            return result.scalar_one_or_none()

    async def get_job_by_session(self, session_id: str) -> GenerationJob | None:
        """按 session_id 查询该会话最新的一个 Job（按主键倒序取第一条），不存在时返回 None。"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenerationJob).where(GenerationJob.session_id == session_id)
                .order_by(GenerationJob.id.desc()).limit(1)
            )
            return result.scalar_one_or_none()

    async def claim_job(self, job_id: str, owner: str, lease_seconds: int) -> GenerationJob | None:
        """原子抢占：仅当 Job 活动、未达上限、且租约空闲/过期/属于自己时才能领取。
        领取即置 running、写租约、attempts+1。rowcount==0 表示没抢到。"""
        now = datetime.now()
        lease_until = now + timedelta(seconds=lease_seconds)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                # 前三个条件必须全部成立（是这个 Job、还活着、还没超重试上限），并且第四组里至少满足一个（租约现在是可以拿的）
                update(GenerationJob)
                .where(
                    GenerationJob.job_id == job_id,
                    GenerationJob.status.in_(ACTIVE_STATUSES),
                    GenerationJob.attempts < GenerationJob.max_attempts,
                    or_(
                        GenerationJob.lease_owner.is_(None),
                        GenerationJob.lease_until.is_(None),
                        GenerationJob.lease_until < now,
                        GenerationJob.lease_owner == owner,
                    ),
                )
                .values(
                    status=RUNNING, lease_owner=owner, lease_until=lease_until,
                    heartbeat_at=now, started_at=now, updated_at=now,
                    attempts=GenerationJob.attempts + 1,
                )
            )
            if not result.rowcount:
                await db.rollback()
                return None
            await db.commit()
            res = await db.execute(select(GenerationJob).where(GenerationJob.job_id == job_id))
            return res.scalar_one_or_none()

    async def heartbeat(self, job_id: str, owner: str, lease_seconds: int) -> bool:
        """续租：只有仍持租约的 owner 能续。返回 False 说明租约被抢走，本地应停止执行。"""
        now = datetime.now()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                update(GenerationJob)
                .where(
                    GenerationJob.job_id == job_id,
                    GenerationJob.status == RUNNING,
                    GenerationJob.lease_owner == owner,
                )
                .values(lease_until=now + timedelta(seconds=lease_seconds), heartbeat_at=now, updated_at=now)
            )
            await db.commit()
            return bool(result.rowcount)

    async def list_reclaimable_jobs(self, limit: int = 20) -> list[GenerationJob]:
        """可恢复 Job：pending，或 running 但租约空/过期，且未达上限。"""
        now = datetime.now()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenerationJob)
                .where(
                    GenerationJob.status.in_(ACTIVE_STATUSES),
                    GenerationJob.attempts < GenerationJob.max_attempts,
                    or_(
                        GenerationJob.status == PENDING,
                        GenerationJob.lease_until.is_(None),
                        GenerationJob.lease_until < now,
                    ),
                )
                .order_by(GenerationJob.id.asc()).limit(limit)
            )
            return list(result.scalars().all())

    async def _mark_terminal(self, job_id: str, status: str, *, owner: str, error_message: str | None = None) -> None:
        """置终态，仅当自己持租约时生效，并清空租约。"""
        now = datetime.now()
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(GenerationJob)
                .where(GenerationJob.job_id == job_id, GenerationJob.lease_owner == owner)
                .values(status=status, lease_owner=None, lease_until=None,
                        error_message=error_message, finished_at=now, updated_at=now)
            )
            await db.commit()

    async def mark_completed(self, job_id: str, owner: str) -> None:
        """将 Job 标记为成功完成（COMPLETED）。仅持有租约的 owner 可操作，同时清空租约。"""
        await self._mark_terminal(job_id, COMPLETED, owner=owner)

    async def mark_failed(self, job_id: str, owner: str, error_message: str) -> None:
        """将 Job 标记为失败（FAILED），并记录错误信息（截断至 4000 字符）。仅持有租约的 owner 可操作。"""
        await self._mark_terminal(job_id, FAILED, owner=owner, error_message=(error_message or "")[:4000])

    async def request_cancel(self, *, job_id: str | None = None, session_id: str | None = None) -> None:
        """外部取消：把匹配的活动 Job 置 cancelled 并清租约。运行中 worker 在 finalize 前复查状态不会再置 completed。"""
        now = datetime.now()
        filters = [GenerationJob.status.in_(ACTIVE_STATUSES)]
        if job_id:
            filters.append(GenerationJob.job_id == job_id)
        if session_id:
            filters.append(GenerationJob.session_id == session_id)
        if len(filters) == 1:  # 没给定位条件，拒绝全表取消
            return
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(GenerationJob).where(and_(*filters)).values(
                    status=CANCELLED, lease_owner=None, lease_until=None,
                    finished_at=now, updated_at=now,
                )
            )
            await db.commit()

    mark_cancelled = request_cancel  # 别名，满足计划里列出的方法名

    async def count_recent_active_jobs(self, recent_seconds: int) -> int:
        """关机时统计近期仍活跃的 Job，用于优雅等待。"""
        threshold = datetime.now() - timedelta(seconds=recent_seconds)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.count()).select_from(GenerationJob).where(
                    GenerationJob.status.in_(ACTIVE_STATUSES),
                    or_(GenerationJob.heartbeat_at >= threshold, GenerationJob.updated_at >= threshold),
                )
            )
            return int(result.scalar() or 0)


generation_job_store = GenerationJobStore()