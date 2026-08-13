# sinan/models/contracts.py
from pydantic import BaseModel, Field, ValidationError
from typing import List


class AnalyzeContract(BaseModel):
    # 当不满足时，会抛出 ValidationError 异常给gates中的_gate_analyze方法，从而返回GateResult(decision="retry")
    requirements: str = Field(..., min_length=20)

    def validate_content(self) -> List[str]:
        errors = []
        # 按需追加业务规则，例如：要求包含"功能"关键词
        return errors


class DesignContract(BaseModel):
    design: str = Field(..., min_length=20)

    def validate_content(self) -> List[str]:
        errors = []
        return errors


class CodeContract(BaseModel):
    html: str = Field(..., min_length=100)

    def validate_content(self) -> List[str]:
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
    verified: bool
    verify_message: str = Field(..., min_length=1)

    def validate_content(self) -> List[str]:
        return []