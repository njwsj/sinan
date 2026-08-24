# sinan/services/session_action_service.py
"""Step 8：会话动作编排（确认 / 迭代 / 中止 / 恢复）。

路由层不直接改表——所有状态流转、建 Job、发事件都收敛到这里，
执行仍由 supervisor / ensure_job_running 驱动，与首轮生成同一套 run_job。

会话动作与状态流转关系：
  confirm  → PAUSED   → ACTIVE   （用户确认设计方案，继续执行）
  iterate  → COMPLETED/PAUSED → ACTIVE  （用户提交迭代反馈，修改已有页面）
  abort    → 任意状态 → FAILED   （用户主动取消，打断正在运行的节点）
  resume   → PAUSED   → ACTIVE   （会话恢复，内部等价于 confirm）
"""
from sinan.models.enums import SessionStatus, PipelineState
from sinan.models.contracts import (
    SessionConfirmRequest, SessionIterateRequest, SessionAbortRequest,
)
from sinan.services.session_store import session_store
from sinan.services.generation_job_store import generation_job_store
from sinan.services.generation_supervisor import ensure_job_running
from sinan.services.generation_event_bus import event_bus
from sinan.services import cancel_registry
from sinan.models import events


def _check_owner(session, user_id: str):
    """校验请求用户是否为会话的所有者。

    过渡期内 user_id 恒为 'anonymous'，此时直接放行，不做权限校验；
    待 Step 3 接入真实认证体系后，将启用严格校验模式。

    Args:
        session: 从数据库取出的会话对象，含 user_id 字段。
        user_id: 发起本次请求的用户 ID。

    Returns:
        None 表示校验通过；
        (403, "无权限操作该会话") 元组表示无权限，调用方应直接返回该错误。
    """
    # 仅当双方 user_id 均非空、且不相等、且请求方不是匿名用户时，才拒绝
    if session.user_id and user_id and session.user_id != user_id and user_id != "anonymous":
        return (403, "无权限操作该会话")
    return None


class SessionActionService:
    """会话动作服务，封装确认、迭代、中止、恢复四种会话操作的完整业务逻辑。

    所有方法遵循统一的处理模式：
    1. 查询会话是否存在；
    2. 校验操作者权限；
    3. 检查当前状态是否允许该操作（前置条件）；
    4. 更新会话状态；
    5. 创建对应的 action Job 并触发执行。

    返回值约定：
    - 成功返回 None；
    - 失败返回 (http_status_code, error_message) 元组，由路由层转换为 HTTP 响应。
    """

    async def confirm(self, session_id, user_id, req: SessionConfirmRequest):
        """处理用户对设计方案的确认操作。

        仅在会话处于 PAUSED（等待确认）状态时合法。
        流程：
          1. 将会话状态从 PAUSED 切换为 ACTIVE；
          2. 清除该会话的取消标记（避免残留的 cancel 信号打断新 Job）；
          3. 在 job_store 中创建 action='confirm' 的新 Job，携带用户确认数据；
          4. 调用 ensure_job_running 通知 supervisor 调度该 Job 立即执行。

        Args:
            session_id: 目标会话 ID。
            user_id: 操作者用户 ID，用于权限校验。
            req: 确认请求体，含 confirmed 标志和可选的追加反馈文本。

        Returns:
            None 表示成功；
            (404, ...) 会话不存在；
            (403, ...) 无权限；
            (400, ...) 当前状态不允许确认（非 PAUSED 状态）。
        """
        s = await session_store.get(session_id)
        if s is None:
            return (404, f"session '{session_id}' 不存在")

        owner_err = _check_owner(s, user_id)
        if owner_err:
            return owner_err

        # 前置条件：只有 PAUSED 状态才能执行确认
        if s.status != SessionStatus.PAUSED.value:
            return (400, "当前会话不在等待确认状态，不能执行确认")

        # 状态切换：PAUSED → ACTIVE
        await session_store.update(session_id, status=SessionStatus.ACTIVE.value)

        # 清除残留取消标记，防止新 Job 被意外打断
        await cancel_registry.clear_async(session_id)

        # 创建 confirm Job 并触发调度
        result = await generation_job_store.create_action_job(
            action="confirm", session_id=session_id, marker=s.marker,
            user_id=user_id, body=req.model_dump(),
        )
        ensure_job_running(result.job.job_id)
        return None

    async def iterate(self, session_id, user_id, req: SessionIterateRequest):
        """处理用户对已生成页面的迭代修改请求。

        与 confirm 不同，迭代不限制前置状态——只要会话存在且有产物，
        无论当前是 COMPLETED 还是 PAUSED 都允许发起新一轮迭代。
        流程：
          1. 清除取消标记（上一轮任务可能残留）；
          2. 将会话状态切换为 ACTIVE；
          3. 创建 action='iterate' 的新 Job，携带用户反馈文本；
          4. 触发 supervisor 调度执行，后续由 generation_runner 分类处理
             （text_replace / partial / structural 三条路径）。

        Args:
            session_id: 目标会话 ID。
            user_id: 操作者用户 ID。
            req: 迭代请求体，含用户的反馈文本（feedback 字段）。

        Returns:
            None 表示成功；
            (404, ...) 会话不存在；
            (403, ...) 无权限。
        """
        s = await session_store.get(session_id)
        if s is None:
            return (404, f"session '{session_id}' 不存在")

        owner_err = _check_owner(s, user_id)
        if owner_err:
            return owner_err

        # 迭代要求已有产物；completed / paused 都允许再迭代，无需检查前置状态

        # 先清取消标记，再切状态，确保顺序正确
        await cancel_registry.clear_async(session_id)
        await session_store.update(session_id, status=SessionStatus.ACTIVE.value)

        # 创建 iterate Job 并触发调度
        result = await generation_job_store.create_action_job(
            action="iterate", session_id=session_id, marker=s.marker,
            user_id=user_id, body=req.model_dump(),
        )
        ensure_job_running(result.job.job_id)
        return None

    async def abort(self, session_id, user_id, req: SessionAbortRequest):
        """处理用户主动取消（中止）当前会话任务的请求。

        中止是即时操作，不创建新 Job，直接在三个层面同时打断：
          1. cancel_registry.cancel_async：向正在运行的节点发送取消信号，
             节点在下一个边界检查点收到信号后停止执行；
          2. generation_job_store.request_cancel：将数据库中该会话的
             活动 Job 状态置为 cancelled，防止 supervisor 重新调度；
          3. session_store.update：将会话状态更新为 FAILED，并记录取消原因。
          4. event_bus.publish：向前端推送 CANCELLED 事件，触发 UI 更新。

        Args:
            session_id: 目标会话 ID。
            user_id: 操作者用户 ID。
            req: 中止请求体（当前版本为空结构，预留扩展）。

        Returns:
            None 表示成功（中止始终视为成功，即使任务已自然结束）；
            (404, ...) 会话不存在；
            (403, ...) 无权限。
        """
        s = await session_store.get(session_id)
        if s is None:
            return (404, f"session '{session_id}' 不存在")

        owner_err = _check_owner(s, user_id)
        if owner_err:
            return owner_err

        # 第一步：向运行中的节点发送取消信号（协程边界打断）
        await cancel_registry.cancel_async(session_id)

        # 第二步：将数据库中活动 Job 置为 cancelled，阻止 supervisor 重调度
        await generation_job_store.request_cancel(session_id=session_id)

        # 第三步：更新会话状态为 FAILED，写入取消原因
        await session_store.update(
            session_id,
            status=SessionStatus.FAILED.value,
            pipeline_state=PipelineState.FAILED.value,
            error_message="cancelled by user",
        )

        # 第四步：向前端推送 CANCELLED 事件，驱动 UI 更新
        await event_bus.publish(
            session_id, events.CANCELLED, events.cancelled_data(),
            marker=s.marker,
        )
        return None

    async def resume(self, session_id, user_id):
        """恢复中断的会话，内部等价于 confirm。

        由于当前使用 MemorySaver（非持久化 Checkpointer），无法真正回放检查点；
        因此 resume 的语义退化为"重新确认并继续跑"，直接复用 confirm 逻辑。

        Args:
            session_id: 目标会话 ID。
            user_id: 操作者用户 ID。

        Returns:
            与 confirm 方法相同的返回值。
        """
        # MemorySaver 非持久，无法真检查点回放；等价于 confirm 续跑
        return await self.confirm(
            session_id, user_id,
            SessionConfirmRequest(confirmed=True, feedback=None),
        )


# 全局单例，路由层直接 import 使用
session_action_service = SessionActionService()
