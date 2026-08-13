from datetime import datetime
from sqlalchemy import BigInteger, String, Text, Integer, DateTime, Enum as SAEnum, JSON, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sinan.models.database import Base
from sinan.models.enums import SessionStatus, PageStatus


class GenSession(Base):
    """会话表：记录每次页面生成任务的完整状态"""
    __tablename__ = "gen_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="自增主键")
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="会话ID")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="用户ID")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, comment="用户需求描述")
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, values_callable=lambda x: [e.value for e in x]),
        default=SessionStatus.PENDING, comment="会话状态"
    )
    current_step: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="当前执行步骤")
    iteration: Mapped[int] = mapped_column(Integer, default=0, comment="修复迭代次数")
    max_iterations: Mapped[int] = mapped_column(Integer, default=3, comment="最大迭代次数上限")
    marker: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="页面标识")
    version: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="版本号")
    preview_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="预览地址")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="累计消耗 token 数")
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0, comment="累计耗时（毫秒）")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    __table_args__ = (
        Index("idx_user_status", "user_id", "status"),
        Index("idx_created", "created_at"),
    )


class GenSessionStep(Base):
    """会话步骤明细表：记录每个步骤的输入输出及执行结果"""
    __tablename__ = "gen_session_step"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属会话ID")
    step: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="步骤名称：receive/analyze/design/code/verify/fix/host"
    )
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="数据方向：input/output")
    input_data: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="步骤输入数据")
    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="步骤输出数据")
    contract_result: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="契约校验结果")
    gate_decision: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="门禁决策结果")
    token_usage: Mapped[int] = mapped_column(Integer, default=0, comment="本步骤消耗 token 数")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, comment="本步骤耗时（毫秒）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")

    __table_args__ = (
        Index("idx_session", "session_id", "step"),
        Index("idx_step_created", "created_at"),
    )


class PageVersion(Base):
    """页面版本表：存储每个页面标识下的多个版本内容"""
    __tablename__ = "page_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    marker: Mapped[str] = mapped_column(String(128), nullable=False, comment="页面标识")
    version: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号")
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="生成的 HTML 内容")
    source_code: Mapped[str | None] = mapped_column(Text, nullable=True, comment="页面源代码")
    status: Mapped[PageStatus] = mapped_column(
        SAEnum(PageStatus, values_callable=lambda x: [e.value for e in x]),
        default=PageStatus.DRAFT, comment="页面状态"
    )
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="页面所有者")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, comment="创建人ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    __table_args__ = (
        UniqueConstraint("marker", "version", name="uk_marker_version"),
        Index("idx_marker", "marker"),
    )
