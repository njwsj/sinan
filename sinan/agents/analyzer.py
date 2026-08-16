# sinan/agents/analyzer.py
import json
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState

SYSTEM_PROMPT = """你是一个需求分析专家。
分析用户的页面需求，输出结构化的需求清单。

输出格式（纯文本，不要 markdown）：
1. 核心功能列表（每条一行）
2. 数据展示要求
3. 交互要点
4. 特殊约束（如：必须用 ECharts、响应式等）

直接输出分析结果，不要任何前缀说明。"""


def _build_att_context(attachments: list) -> str:
    """
    从 state["attachments"] 构造需求分析用的数据上下文。
    对齐原项目：列出前20个字段名 + 行数 + 完整 rows（供 LLM 理解数据结构）。
    """
    if not attachments:
        return ""
    parts = []
    for att in attachments:
        parsed = att.get("parsed") or {}
        cols = att.get("columns") or parsed.get("columns") or []
        rows = parsed.get("rows") or []
        row_count = att.get("row_count") or parsed.get("row_count") or len(rows)
        filename = att.get("filename", "未知文件")

        info = f"- {filename}: {', '.join(str(c) for c in cols[:20])}"
        if row_count:
            info += f" ({row_count}行)"
        if rows:
            info += f"\n  数据样本（前5行）: {json.dumps(rows[:5], ensure_ascii=False)}"
        parts.append(info)
    return "\n\n用户上传的数据文件(请基于此数据进行需求分析):\n" + "\n".join(parts)


class AnalyzerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        user_content = state["prompt"]

        # 从结构化 attachments 读取数据，各自构造上下文注入 prompt
        att_context = _build_att_context(state.get("attachments", []))
        if att_context:
            user_content = user_content + att_context

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        requirements = await self.llm.chat(messages, temperature=0.3)
        return {"requirements": requirements}
