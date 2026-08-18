# sinan/api/routes/audit.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep, GenSession

router = APIRouter()


@router.get("/generate/{session_id}/audit")
async def get_audit(session_id: str):
    """
    返回指定会话的完整执行审计轨迹。
    包含每个步骤的输入/输出、门禁决策、时间戳。
    """
    async with AsyncSessionLocal() as db:
        # 先确认 session 存在
        session_result = await db.execute(
            select(GenSession).where(GenSession.id == session_id)
        )
        session = session_result.scalar_one_or_none()
        if session is None:
            return JSONResponse(status_code=404, content={"detail": f"会话 {session_id} 不存在"})

        # 查询所有步骤记录
        steps_result = await db.execute(
            select(GenSessionStep)
            .where(GenSessionStep.session_id == session_id)
            .order_by(GenSessionStep.created_at)
        )
        steps = steps_result.scalars().all()

    audit_trail = [
        {
            "step": s.step,
            "direction": s.direction,
            "output": s.output_data,
            "gate_decision": s.gate_decision,
            "timestamp": s.created_at.isoformat() if s.created_at else None,
        }
        for s in steps
    ]

    return {
        "session_id": session_id,
        "status": session.status,
        "pipeline_state": session.pipeline_state,
        "prompt": session.prompt,
        "total_steps": len(steps),
        "audit_trail": audit_trail,
    }