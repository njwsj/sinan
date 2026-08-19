# sinan/agents/router.py
"""Router Agent：识别意图并抽取页面生成参数。对齐参考 page/agents/router.py。"""
from __future__ import annotations

import json
import logging

from sinan.agents.llm import LLMClient
from sinan.agents.state import GenerationState
from sinan.models.enums import PipelineState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个页面生成路由器。分析用户需求，判断意图并提取关键信息。
以JSON格式返回：
{
  "intent": "create | modify | template | data_query",
  "confidence": 0.0-1.0,
  "extracted_info": {
    "page_type": "dashboard | report | analysis | custom",
    "data_source": "excel | system | api | mock | static",
    "reference_template": null,
    "modification_scope": null
  }
}
只返回JSON，不要其他内容。"""

_FALLBACK_INTENT = {
    "intent": "create",
    "confidence": 0.5,
    "extracted_info": {"page_type": "dashboard"},
}


def _parse_intent(text: str) -> dict:
    """解析 router 输出；失败返回兜底 intent（与参考一致，不抛异常）。"""
    raw = (text or "").strip()
    if raw.startswith("```"):                     # sinan 增量：参考未处理 ``` 包裹
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3].rstrip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("router: intent JSON 解析失败，使用兜底值")
        return dict(_FALLBACK_INTENT)
    if not isinstance(parsed, dict) or "intent" not in parsed:
        return dict(_FALLBACK_INTENT)
    parsed.setdefault("confidence", 0.5)
    parsed.setdefault("extracted_info", {})
    return parsed


class RouterAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": state.get("user_input", "")},
        ]
        intent = _parse_intent(await self.llm.chat(messages, temperature=0.1))
        logger.info("router: intent=%s confidence=%s",
                    intent.get("intent"), intent.get("confidence"))
        return {
            "intent": intent,
            "status": "analyzing",
            "pipeline_state": PipelineState.INGESTION.value,
        }