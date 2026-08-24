# sinan/models/contracts.py
"""流水线各步骤的结构化契约模型。

对齐参考 page/models/contracts.py：每个 PipelineState 有一个输出契约，
harness/contracts.py 的 ContractValidator 按步骤取契约做 model_validate，
校验失败不抛异常，而是把错误写进 state["contract_errors"] 供后续排查。

与 Step 6 之前的差异：原先只有 AnalyzeContract/DesignContract/CodeContract/VerifyContract
四个「字符串长度 + doctype」级别的弱契约，且校验逻辑写在契约的 validate_content() 里由
gates.py 调用。Step 7 起改为参考的结构化契约，弱契约整体删除。
"""
from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


# ─── Step 1: Ingestion ───────────────────────────────
class DataSourceConfig(BaseModel):
    """数据源配置。type: api / static / database / file。"""

    type: str
    endpoint: str | None = None
    schema_url: str | None = None
    sample_data: dict | None = None


class IngestionInput(BaseModel):
    """摄取步骤的原始输入。"""

    raw_requirement: str = Field(..., min_length=10, max_length=10000)
    data_sources: list[DataSourceConfig] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)


class NormalizedRequirement(BaseModel):
    """归一化后的需求。page_type: dashboard / report / analysis / custom。"""

    title: str
    description: str
    page_type: str
    target_platform: str = "pc"
    features: list[str] = Field(default_factory=list)
    data_fields: list[dict] = Field(default_factory=list)


class IngestionOutput(BaseModel):
    """摄取步骤输出。"""

    requirement: NormalizedRequirement
    data_schema: dict = Field(default_factory=dict)
    validation_report: dict = Field(default_factory=dict)


# ─── Step 2: Analysis ───────────────────────────────
class FunctionalModule(BaseModel):
    """分析阶段识别出的单个功能模块。priority: must / should / nice-to-have。"""

    module_id: str
    name: str
    description: str
    priority: str = "must"
    data_dependencies: list[str] = Field(default_factory=list)
    interaction_type: str = "display"


class AnalysisOutput(BaseModel):
    """分析步骤输出。

    注意：参考项目 analyst 实际产出的是 {"_format": "markdown", "_content": ...,
    "confidence_score": ..., "confirmation_digest": ...}，并不满足 functional_modules
    的 min_length=1，因此 ANALYSIS 步骤的 contract 校验在参考里是稳定失败并被记进
    contract_errors 的（不阻断流程）。sinan 保持同样行为以对齐黑盒表现。
    """

    template_analysis: dict = Field(default_factory=dict)
    functional_modules: list[FunctionalModule] = Field(min_length=1)
    data_plan: dict = Field(default_factory=dict)
    style_profile: dict = Field(default_factory=dict)
    confirmation_digest: str
    confidence_score: float = Field(ge=0.0, le=1.0)


# ─── Step 3: Design ───────────────────────────────
class ComponentNode(BaseModel):
    """递归组件树节点。"""

    component_id: str
    component_type: str
    props: dict = Field(default_factory=dict)
    data_binding: dict | None = None
    children: list["ComponentNode"] = Field(default_factory=list)


ComponentNode.model_rebuild()


class DesignOutput(BaseModel):
    """设计步骤输出。"""

    layout: dict
    component_tree: ComponentNode
    interactions: list[dict] = Field(default_factory=list)
    data_bindings: list[dict] = Field(default_factory=list)
    style_tokens: dict = Field(default_factory=dict)


# ─── Step 4: Generation ───────────────────────────────
class CodeFile(BaseModel):
    """单个生成文件。role: component / style / logic / entry。"""

    path: str
    content: str
    language: str = "html"
    role: str = "entry"


class GenerationOutput(BaseModel):
    """代码生成步骤输出。当前实际只产出单文件 index.html。"""

    files: list[CodeFile] = Field(min_length=1)
    entry_point: str = "index.html"
    dependencies: list[dict] = Field(default_factory=list)


# ─── Step 5: Validation ───────────────────────────────
class ValidationIssue(BaseModel):
    """单条验证问题。所有 validator 统一输出这个结构。"""

    issue_id: str
    severity: str          # P0 / P1 / P2
    category: str          # requirement / template / data / syntax / render / ...
    description: str
    location: str | None = None
    suggestion: str | None = None


def compute_quality_score(issues: list["ValidationIssue"]) -> float:
    """由问题列表计算 [0.0, 1.0] 的质量分。

    扣分权重（对齐参考 page/models/contracts.py:122）：
      P0 → 0.30（阻断）
      P1 → 0.10（显著）
      P2 → 0.02（轻微）
    多条累加，下限截断到 0.0。
    """
    _PENALTIES: dict[str, float] = {"P0": 0.30, "P1": 0.10, "P2": 0.02}
    penalty = sum(_PENALTIES.get(i.severity, 0.0) for i in issues)
    return max(0.0, round(1.0 - penalty, 2))


class RepairRecord(BaseModel):
    """单轮修复记录。"""

    round: int
    issues_found: list[ValidationIssue] = Field(default_factory=list)
    issues_resolved: list[str] = Field(default_factory=list)
    issues_remaining: list[str] = Field(default_factory=list)


class ValidationOutput(BaseModel):
    """最终验证结果 + 修复历史。"""

    passed: bool
    total_rounds: int = Field(ge=1, le=3)
    final_code: GenerationOutput | None = None
    repair_history: list[RepairRecord] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0)


# ─── Step 7: Iteration ───────────────────────────────
class RouteDecision(BaseModel):
    """迭代路由决策：修改请求应该从哪个步骤重新进入流水线（Step 8 使用）。"""

    target_step: str        # design / generation
    reason: str
    change_scope: str       # structural / partial
    affected_modules: list[str] = Field(default_factory=list)
    preserved_modules: list[str] = Field(default_factory=list)


# ─── API Request/Response ───────────────────────────
class GenerateRequest(BaseModel):
    """页面生成请求体（Step 1 已对齐参考，本 Step 不变）。"""

    prompt: str = Field(..., min_length=2)
    session_id: str | None = None
    marker: str | None = None
    attachments: list[dict] = Field(default_factory=list)
    preset: str | None = None
    template_id: str | None = None
    prompt_template_id: str | None = None
    datasources: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)
    skill_keys: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("skill_keys", "skillKeys"),
    )
    mode: str | None = None

# ─── Step 8: 会话动作请求 ───────────────────────────
class SessionConfirmRequest(BaseModel):
    """用户对低置信度需求的确认。confirmed=false 表示拒绝并附反馈。"""

    confirmed: bool = True
    feedback: str | None = None


class SessionIterateRequest(BaseModel):
    """已完成页面的多轮修改反馈。mode 可显式指定路由（design/generation/direct_edit）。"""

    feedback: str = Field(..., min_length=1)
    mode: str | None = None
    attachments: list[dict] = Field(default_factory=list)


class SessionAbortRequest(BaseModel):
    """中止当前会话的生成/迭代。reason 仅用于记录。"""

    reason: str | None = None