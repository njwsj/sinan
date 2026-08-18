from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from sinan.models.database import Base
from sinan.models.enums import JobStatus, PageStatus, PipelineState, SessionStatus


class GenSession(Base):
    """会话表：一次页面生成会话的完整上下文。

    对齐参考 generation_session（page/models/tables.py:25）。
    status 与 pipeline_state 分工：
      - status：会话生命周期（active/paused/completed/failed/archived）
      - pipeline_state：流水线跑到哪一阶段（init…delivered/failed）
    """
    __tablename__ = "gen_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="自增主键")
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="会话ID")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="用户ID")
    marker: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="页面标识")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, comment="用户需求描述")
    title: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="会话标题")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SessionStatus.ACTIVE.value, index=True,
        comment="会话状态：active/paused/completed/failed/archived",
    )
    pipeline_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PipelineState.INIT.value,
        comment="流水线阶段：init…delivered/failed",
    )
    current_step: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="当前执行步骤")
    requirement_doc: Mapped[str | None] = mapped_column(Text, nullable=True, comment="需求文档（analyzer 产出）")
    messages: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="多轮对话消息")
    attachments: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="附件元信息列表")
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="使用的模板ID")
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="修复迭代次数")
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=3, comment="最大迭代次数上限")
    fix_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="累计修复轮数")
    verification_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="最近一次验证得分")
    gate_reports: Mapped[str | None] = mapped_column(Text, nullable=True, comment="门禁报告（JSON 文本）")
    model_versions: Mapped[str | None] = mapped_column(Text, nullable=True, comment="模型版本信息（JSON 文本）")
    version: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="产出的页面版本号")
    preview_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="预览地址")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="累计消耗 token 数")
    total_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="累计耗时（毫秒）")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    # 逻辑删除：参考项目由外部删除链路写入，本服务只读用于过滤
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True, comment="是否逻辑删除")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="删除时间")
    deleted_by: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="删除人")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    __table_args__ = (
        Index("idx_user_status", "user_id", "status"),
        Index("idx_created", "created_at"),
    )


class GenSessionStep(Base):
    """会话步骤明细表：记录每个步骤的输入输出及执行结果。

    sinan 独有：参考侧靠 generation_session.messages + generation_artifact 承载，
    本表语义不与参考逐字对齐，作为本项目的细粒度审计。
    """
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
    token_usage: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="本步骤消耗 token 数")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="本步骤耗时（毫秒）")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")

    __table_args__ = (
        Index("idx_session", "session_id", "step"),
        Index("idx_step_created", "created_at"),
    )


class GenerationJob(Base):
    """生成任务表：可持久化、可租约、可恢复的任务生命周期（Step 4 建立）。"""
    __tablename__ = "generation_job"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="自增主键")
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="任务ID")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属会话ID")
    marker: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="页面标识")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="用户ID")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=JobStatus.PENDING.value,
        comment="任务状态：pending/running/waiting/completed/failed/cancelled",
    )
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, comment="重放生成所需的请求负载")
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="租约持有worker")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="租约到期时间")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近心跳时间")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已尝试次数")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3, comment="最大尝试次数")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    __table_args__ = (
        Index("idx_job_session", "session_id"),
        Index("idx_job_status", "status"),
        Index("idx_job_lease", "lease_until"),
    )


class GenerationArtifact(Base):
    """流水线中间产物：analysis / design / verification / code 快照等。

    对齐参考 generation_artifact（page/models/tables.py:51）。
    content 与 bos_path 二选一：小产物直接入库，大产物 Step 9 起走对象存储。
    """
    __tablename__ = "generation_artifact"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所属会话ID")
    artifact_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="产物类型：analysis/design/code/verification/fix"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="同类型产物版本号")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="产物正文")
    bos_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="对象存储路径")
    # 列名必须是 metadata 以对齐参考，但 metadata 是 SQLAlchemy 声明式保留属性名，故属性名取 meta
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True, comment="附加元信息")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True, comment="是否逻辑删除")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="删除时间")
    deleted_by: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="删除人")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("session_id", "artifact_type", "version", name="uk_artifact_session_type_version"),
    )


class Page(Base):
    """页面主表：marker 维度的页面元数据与发布状态。

    对齐参考 page（page/models/tables.py:90）。
    本 Step 起 PageVersion 不再承担主表职责：
      - Page 保存 owner / status / current_version / published_version
      - PageVersion 只保存不可变版本快照
    """
    __tablename__ = "page"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    marker: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="页面标识")
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="创建来源会话ID")
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="页面标题")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="页面描述")
    owner: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="所有者用户ID")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PageStatus.DRAFT.value, index=True,
        comment="页面状态：draft/preview/published/archived",
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="当前最新版本号")
    published_version: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="已发布版本号")
    published_to: Mapped[str] = mapped_column(String(256), nullable=False, default="", comment="发布目标")
    prompt_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="需求摘要")
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="封面图地址")
    tags: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="标签，逗号分隔")
    allowed_datasources: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="允许访问的数据源")
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="质量分")
    last_gate_report: Mapped[str | None] = mapped_column(Text, nullable=True, comment="最近门禁报告")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )


class PageVersion(Base):
    """页面版本快照表（不可变）。

    对齐参考 page_version（page/models/tables.py:113）。
    差异：参考正文只在 BOS，sinan 在 Step 9 接对象存储前继续用 html_content 兜底，
    因此 bos_path/file_list 允许为空，Step 9 完成后收紧为 nullable=False。
    """
    __tablename__ = "page_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    marker: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="页面标识")
    version: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号")
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="HTML 正文（Step 9 前的存储兜底）")
    source_code: Mapped[str | None] = mapped_column(Text, nullable=True, comment="页面源代码")
    bos_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="对象存储路径（Step 9）")
    entry_file: Mapped[str] = mapped_column(String(128), nullable=False, default="index.html", comment="入口文件名")
    file_list: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文件清单（JSON 文本）")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="正文哈希，用于去重")
    code_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="代码字节数")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="文件数")
    note: Mapped[str] = mapped_column(String(256), nullable=False, default="", comment="版本备注")
    security_scan: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="安全扫描：0未扫/1通过/2拦截")
    scan_result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="安全扫描结果")
    harness_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Harness 验证得分")
    repair_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="修复轮数")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="创建人ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")

    __table_args__ = (
        UniqueConstraint("marker", "version", name="uk_marker_version"),
        Index("idx_marker", "marker"),
    )


class Attachment(Base):
    """附件表：上传文件的元信息。

    注意：参考项目没有此表，附件元信息存在 generation_session.attachments JSON 里。
    本表按实施方案预建，但本 Step 不切流量——attachments JSON 仍是权威来源，
    避免双写不一致。Step 9 统一附件存储时再决定是否以本表为准。
    """
    __tablename__ = "attachment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    file_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="文件ID")
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="所属会话ID")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="上传者")
    file_name: Mapped[str] = mapped_column(String(256), nullable=False, comment="原始文件名")
    file_type: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="文件类型：excel/csv/image")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="字节数")
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False, default="", comment="本地或对象存储路径")
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="解析后行数")
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True, comment="解析元信息：列名等")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")


class SkillDefinition(Base):
    """Skill 定义表（Step 12 使用，本 Step 只建表）。对齐参考 skill_definition。"""
    __tablename__ = "skill_definition"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    skill_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, comment="Skill 唯一键")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0", comment="版本")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Skill 正文")
    bos_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="对象存储路径")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="disabled", index=True, comment="启用状态")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="internal", comment="可见范围")
    output_type: Mapped[str] = mapped_column(String(32), nullable=False, default="data", comment="产出类型")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="创建人")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )


class PageTemplate(Base):
    """页面模板表（Step 11 使用，本 Step 只建表）。对齐参考 page_template。"""
    __tablename__ = "page_template"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    template_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="模板ID")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="模板名")
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="", comment="描述")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="一级分类")
    sub_category: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="二级分类")
    bos_path: Mapped[str] = mapped_column(String(256), nullable=False, comment="模板存储路径")
    thumbnail_path: Mapped[str] = mapped_column(String(256), nullable=False, default="", comment="缩略图路径")
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="html", comment="模板类型：html/prompt")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True, comment="状态")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="创建人")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )