# sinan/services/generation_supervisor.py
import asyncio
import logging
from contextlib import suppress

from sinan.services.generation_job_store import generation_job_store
from sinan.services.generation_runner import generation_runner

logger = logging.getLogger(__name__)

# supervisor 每隔多少秒扫描一次可恢复的 Job
# 值越小响应越快，但数据库查询频率越高
_SUPERVISOR_SECONDS = 15

# 当前进程正在执行的 Job task 字典
# key: job_id，value: 对应的 asyncio.Task
# Job 完成后会通过 done_callback 自动从字典中移除
_local_tasks: dict[str, asyncio.Task] = {}

# supervisor 后台循环任务的引用，用于启动/停止控制
# None 表示 supervisor 当前未运行
_supervisor_task: asyncio.Task | None = None

# 停止信号开关（目前仅用于扩展，实际停止由 cancel 驱动）
_stop_event: asyncio.Event | None = None


def ensure_job_running(job_id: str) -> None:
    """确保当前进程已为指定 Job 启动了一个执行 task（幂等）。

    如果该 Job 的 task 已存在且尚未结束，则直接返回，不重复创建。
    如果不存在或已结束，则创建新 task 并注册 done_callback：
    task 完成后自动从 _local_tasks 中移除，避免字典无限增长。

    典型调用方：supervisor_loop 在每次扫描到可恢复 Job 时调用。
    """
    task = _local_tasks.get(job_id)
    if task and not task.done():
        return
    task = asyncio.create_task(generation_runner.run_job(job_id), name=f"gen-job-{job_id}")
    task.add_done_callback(lambda t: _local_tasks.pop(job_id, None) if _local_tasks.get(job_id) is t else None)
    _local_tasks[job_id] = task


async def supervisor_loop() -> None:
    """supervisor 的主循环，每隔 _SUPERVISOR_SECONDS 秒执行一次扫描。

    每次循环：
    1. 从数据库查出所有可恢复的 Job（pending 或租约过期的 running）
    2. 对每个 Job 调用 ensure_job_running，确保本进程有对应 task 在跑
    3. 等待下一个周期

    异常处理：
    - CancelledError 直接上抛，让调用方（stop_supervisor）能正常取消
    - 其他异常记录日志后继续下一轮，避免单次扫描失败导致 supervisor 停止
    """
    while True:
        try:
            for job in await generation_job_store.list_reclaimable_jobs():
                ensure_job_running(job.job_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("generation supervisor tick failed")
        await asyncio.sleep(_SUPERVISOR_SECONDS)


async def start_supervisor() -> None:
    """启动 supervisor 后台循环（幂等）。

    如果 supervisor 已在运行则直接返回，不重复启动。
    启动后 supervisor 会在后台持续扫描并恢复 Job，直到 stop_supervisor 被调用。

    典型调用方：应用启动时的 lifespan 钩子（如 FastAPI 的 startup 事件）。
    """
    global _supervisor_task, _stop_event
    if _supervisor_task and not _supervisor_task.done():
        return
    _stop_event = asyncio.Event()
    _supervisor_task = asyncio.create_task(supervisor_loop(), name="gen-job-supervisor")
    logger.info("generation job supervisor started")


async def stop_supervisor() -> None:
    """优雅停止 supervisor 及所有正在执行的 Job task。

    执行步骤：
    1. 置位 _stop_event（扩展用，当前循环以 cancel 为主要停止手段）
    2. cancel supervisor 循环 task，并等待其退出
    3. cancel 所有 _local_tasks 中的 Job task
    4. 等待所有 Job task 退出（忽略 CancelledError）
    5. 清空 _local_tasks，重置全局状态

    注意：cancel 不保证 Job 立即停止，只是发送取消信号；
    generation_runner 内部需要配合处理 CancelledError 才能真正停下来。

    典型调用方：应用关闭时的 lifespan 钩子（如 FastAPI 的 shutdown 事件）。
    """
    global _supervisor_task, _stop_event
    if _stop_event:
        _stop_event.set()
    if _supervisor_task:
        _supervisor_task.cancel()
        with suppress(asyncio.CancelledError):
            await _supervisor_task
    for task in list(_local_tasks.values()):
        task.cancel()
    for task in list(_local_tasks.values()):
        with suppress(asyncio.CancelledError):
            await task
    _local_tasks.clear()
    _supervisor_task = None
    _stop_event = None
    logger.info("generation job supervisor stopped")