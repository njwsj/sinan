from enum import Enum

"""
枚举取值与参考项目 page/models/enums.py 对齐。

注意：本文件所有枚举只作为 Python 侧取值约束，数据库列统一使用 String(32)。
原因是数据库 ENUM 每新增一个状态都要 ALTER TABLE，而 Step 7/8 仍会继续扩状态。
"""


class PipelineState(str, Enum):
    """流水线阶段（参考 page/models/enums.py:6）。

    init → ingestion → analysis → user_confirm → design
         → generation → validation → preview → user_review → delivered
    任意阶段可跳到 failed。
    """
    INIT = "init"
    INGESTION = "ingestion"
    ANALYSIS = "analysis"
    USER_CONFIRM = "user_confirm"
    DESIGN = "design"
    GENERATION = "generation"
    VALIDATION = "validation"
    PREVIEW = "preview"
    USER_REVIEW = "user_review"
    DELIVERED = "delivered"
    FAILED = "failed"


class SessionStatus(str, Enum):
    """会话生命周期（参考 page/models/enums.py:33）。

    active → paused          # 等待用户确认/补充
    paused → active          # resume
    active → completed / failed
    active/paused → archived

    与 Step 5 及之前的旧库差异：旧 pending/running/awaiting_input 已废弃。
    - 旧 pending/running   → ACTIVE（真实运行进度看 GenerationJob.status 与 pipeline_state）
    - 旧 awaiting_input     → PAUSED
    """
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class JobStatus(str, Enum):
    """生成任务状态。Step 4 用的是裸字符串常量，这里收敛成枚举。

    pending → running → completed
    pending/running → failed / cancelled
    running → waiting        # 等待用户确认（Step 8 使用）
    waiting → running
    """
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PageStatus(str, Enum):
    """页面状态。

    draft → preview → published → archived
    preview 表示已生成可预览但未对外发布（参考 page 表 status 默认 draft）。
    """
    DRAFT = "draft"
    PREVIEW = "preview"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PageSource(str, Enum):
    """页面创建来源（参考 page/models/enums.py:43）。"""
    GENERATION = "generation"
    MANUAL = "manual"
    TEMPLATE = "template"

class AgentRole(str, Enum):
    ROUTER = "router"; ANALYST = "analyst"; DESIGNER = "designer"
    CODER = "coder"; VERIFIER = "verifier"; FIXER = "fixer"


class IssueSeverity(str, Enum):
    """P0/P1 阻断，P2 不阻断；扣分 0.30/0.10/0.02。"""
    P0 = "P0"; P1 = "P1"; P2 = "P2"


class IssueCategory(str, Enum):
    """security / a11y 参考也只预留枚举无实现，本 Step 同样不实现。"""
    REQUIREMENT = "requirement"; TEMPLATE = "template"; DATA = "data"
    SYNTAX = "syntax"; RENDER = "render"; STYLE = "style"
    SECURITY = "security"; A11Y = "a11y"


class RepairStrategy(str, Enum):
    CONSERVATIVE = "conservative"; MODERATE = "moderate"; AGGRESSIVE = "aggressive"


class ChangeScope(str, Enum):
    """Step 8 iteration_router 使用，本 Step 只占位。"""
    STRUCTURAL = "structural"; PARTIAL = "partial"


class GateDecision(str, Enum):
    """sinan 增量：参考用 passed + requires_user 表达。"""
    PROCEED = "proceed"; RETRY = "retry"; FIX = "fix"
    BLOCK = "block"; WAIT_USER = "wait_user"