# sinan/models/contracts.py
from pydantic import AliasChoices, BaseModel, Field
from typing import List

"""
Pydantic 契约模型用来约束每个 Agent 的输出格式。
例如 Analyzer 必须输出某些关键字段，Coder 输出的 HTML 至少要有 100 个字符。这样一旦 LLM 输出偏轨，Pydantic 校验就会报错，触发重试而不是把垃圾数据传给下一步。

每个契约类统一提供 `validate_content()` 方法，封装该步骤的业务校验规则，返回错误列表。
门禁引擎（gates.py）调用这个方法，只负责根据结果做路由决策，不自己实现校验逻辑。
"""


class AnalyzeContract(BaseModel):
    """Analyzer 输出契约：结构化需求描述必须包含这些核心字段。"""
    requirements: str = Field(..., min_length=20,
                              description="结构化需求清单，至少 20 个字符")

    def validate_content(self) -> List[str]:
        """业务内容校验，返回错误列表（空列表 = 通过）。"""
        errors = []
        # Pydantic 的 min_length 已保证长度，这里可追加更多业务规则
        # 例如：要求包含"功能"或"数据"等关键词（按需开启）
        return errors


class DesignContract(BaseModel):
    """Designer 输出契约：设计方案必须包含布局和配色描述。"""
    design: str = Field(..., min_length=20,
                        description="页面设计方案，至少 20 个字符")

    def validate_content(self) -> List[str]:
        """业务内容校验，返回错误列表（空列表 = 通过）。"""
        errors = []
        # 例如：要求包含布局或配色关键词（按需开启）
        return errors


class CodeContract(BaseModel):
    """Coder 输出契约：生成的 HTML 必须满足最低结构要求。"""
    html: str = Field(..., min_length=100, description="生成的 HTML，至少 100 字符")

    def validate_content(self) -> List[str]:
        """HTML 结构校验，返回错误列表（空列表 = 通过）。"""
        errors = []
        html_lower = self.html.lower()
        if "<!doctype" not in html_lower[:200]:
            errors.append("缺少 <!DOCTYPE html>")
        if "<html" not in html_lower:
            errors.append("缺少 <html> 标签")
        if "<body" not in html_lower:
            errors.append("缺少 <body> 标签")
        return errors


class VerifyContract(BaseModel):
    """Verifier 输出契约：校验结果必须明确给出通过/失败。"""
    verified: bool
    verify_message: str = Field(..., min_length=1)

    def validate_content(self) -> List[str]:
        return []

class GenerateRequest(BaseModel):
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