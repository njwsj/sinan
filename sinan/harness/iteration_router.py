# -*- coding: UTF-8 -*-
"""Iteration router - classifies user feedback and routes to Design or Generation."""
from __future__ import annotations

import json
import re

from page.agents.llm import llm
from page.models.enums import ChangeScope

# Signal keywords for quick classification
_STRUCTURAL_SIGNALS = [
    "重新布局", "换个结构", "加一个新模块", "删掉这个区域",
    "整体风格换", "改成Tab", "加个侧边栏", "改导航", "大改", "重做",
    "重新生成", "重新设计", "重新做", "完全重新", "全部重新", "从头",
    "regenerate", "redo",
]
_PARTIAL_SIGNALS = [
    "改个颜色", "字号调大", "间距调整", "换个图标", "按钮文案",
    "加个loading", "排序改成", "加个判断", "换个图表", "微调",
]

# Signals that mean "just keep generating / retry" — treat as partial regeneration.
# Use full-string match for short/ambiguous words to avoid false positives.
_CONTINUE_SIGNALS_CONTAINS = [
    "继续生成", "继续完善", "继续完成", "接着生成", "再生成一下", "重新生成一下",
    "继续做", "再试一次", "再来一次",
    "continue", "retry",
]
_CONTINUE_SIGNALS_EXACT = {
    "继续", "ok", "好的", "可以", "确认", "确定", "没问题", "好", "再试",
}

# Patterns for text replacement detection
_REPLACE_PATTERNS = [
    # 「旧值」改为「新值」 — 新旧均带引号
    re.compile(
        r'[""「【](.+?)[""」】]\s*[，,：:]*\s*'
        r'(?:改为|改成|换成|替换为|修改为|变为|变成)\s*[，,]?\s*[""「【](.+?)[""」】]'
    ),
    # 「旧值」：改为，新值 — 旧值带引号、新值无引号（支持冒号/逗号分隔符）
    re.compile(
        r'[""「【](.+?)[""」】]\s*[，,：:]+\s*'
        r'(?:改为|改成|换成|替换为|修改为|变为|变成)\s*[，,]?\s*([^，,。""「【】"\n]+?)(?:[，,。]|$)'
    ),
    re.compile(
        r'把\s*[""「【](.+?)[""」】]\s*'
        r'(?:改为|改成|换成|替换为|修改为|变为|变成)\s*[""「【](.+?)[""」】]'
    ),
    re.compile(
        r'将\s*[""「【](.+?)[""」】]\s*'
        r'(?:改为|改成|换成|替换为|修改为|变为|变成)\s*[""「【](.+?)[""」】]'
    ),
    # Without quotes: "A ，修改为 B" or "A，改为B"
    re.compile(
        r'(.+?)\s*[，,]\s*'
        r'(?:改为|改成|换成|替换为|修改为|变为|变成)\s*(.+?)(?:[，,。]|$)'
    ),
]


# CSS id selector pattern: starts with '#' followed by valid id characters
_CSS_ID_SELECTOR_RE = re.compile(r'^#([\w-]+)$')


def detect_text_replacement(feedback: str) -> list[tuple[str, str]] | None:
    """检测用户反馈中的文本替换指令，返回替换对列表或 None。

    逐个应用 _REPLACE_PATTERNS 中定义的正则表达式，从用户反馈中提取所有「旧值→新值」对。
    对同一对去重后按出现顺序返回。

    Args:
        feedback: 用户的自然语言反馈文本。

    Returns:
        若检测到替换指令，返回 [(old_text, new_text), ...] 列表；
        否则返回 None。
        每个元组中 old_text 可能是：
        - 普通字符串：调用方应在代码中做字面量替换；
        - CSS id 选择器（以 '#' 开头）：调用方应定位对应 id 元素并替换其文本内容。
    """
    replacements = []
    seen = set()
    for pat in _REPLACE_PATTERNS:
        for m in pat.finditer(feedback):
            old, new = m.group(1).strip(), m.group(2).strip()
            key = (old, new)
            if key not in seen:
                seen.add(key)
                replacements.append(key)
    return replacements if replacements else None


def apply_text_replacements(code: str, replacements: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """将文本替换对应用到 HTML 代码上，返回更新后的代码与已执行替换的描述列表。

    按顺序处理 replacements 中的每一对，支持两种替换模式：

    1. 普通字符串替换：
       在代码中直接做字面量 str.replace()，将所有出现的 old_text 替换为 new_text。

    2. CSS id 选择器替换（old_text 以 '#' 开头，如 '#submit-btn'）：
       通过正则定位含有对应 id 属性的开标签，然后仅替换该开标签之后、
       下一个 '<' 之前的直接文本节点内容（即直接子文本，不涉及子标签）。
       这样可以保留子标签结构，同时避免非贪婪正则在嵌套同名标签下的错误匹配。

    Args:
        code: 原始 HTML 代码字符串。
        replacements: detect_text_replacement() 返回的 [(old_text, new_text), ...] 列表。

    Returns:
        (updated_code, applied_descriptions) 元组：
        - updated_code: 替换后的 HTML 代码；
        - applied_descriptions: 成功执行的替换描述列表，格式为「旧值」→「新值」，
          未匹配到的替换对不会出现在此列表中。
    """
    applied = []
    for old_text, new_text in replacements:
        m = _CSS_ID_SELECTOR_RE.match(old_text)
        if m:
            # CSS selector path: find the opening tag, then replace the direct text
            # node that immediately follows it (everything up to the first '<').
            element_id = m.group(1)
            open_tag_re = re.compile(
                r'<\w+[^>]*\bid\s*=\s*["\']' + re.escape(element_id) + r'["\'][^>]*>',
            )
            tag_match = open_tag_re.search(code)
            if tag_match:
                after = tag_match.end()
                # Find end of direct text node (everything up to next '<')
                next_lt = code.find('<', after)
                if next_lt == -1:
                    next_lt = len(code)
                # Replace the direct text node with new_text
                code = code[:after] + new_text + code[next_lt:]
                applied.append(f"「{old_text}」→「{new_text}」")
        else:
            # Plain string replacement
            if old_text in code:
                code = code.replace(old_text, new_text)
                applied.append(f"「{old_text}」→「{new_text}」")
    return code, applied


async def classify_iteration(
    feedback: str,
    context: dict,
    history: list[dict] | None = None,
    *,
    llm=None,
) -> dict:
    """对用户的迭代反馈进行意图分类，返回路由决策字典。

    分类按以下优先级依次执行，一旦命中即返回，不继续后续步骤：

    1. 文本替换检测（最高优先级）：
       调用 detect_text_replacement() 检查是否包含「旧值→新值」指令。
       命中时直接返回 target_step='text_replace'，无需 AI 介入。

    2. 快捷信号词匹配（继续/确认类）：
       若反馈为"继续"、"ok"、"再试一次"等简短确认语，视为局部重新生成，
       跳过 AI 分类，直接返回 target_step='generation', change_scope='partial'。

    3. 规则关键词打分：
       统计结构性信号词（_STRUCTURAL_SIGNALS）和局部调整信号词（_PARTIAL_SIGNALS）
       的命中数量，若某类明显占优则直接返回对应结果，置信度 0.9。

    4. AI 分类（兜底）：
       前三步均未命中时，将完整对话历史连同当前反馈发送给 LLM，
       要求返回 structural / partial / unclear 三选一的 JSON 结果。
       - structural → target_step='design'（需重新设计页面结构）
       - partial    → target_step='generation'（仅修改代码细节）
       - unclear    → target_step='clarify'（意图不明，需向用户追问）
       LLM 调用失败或返回非法 JSON 时，兜底为 partial，不阻塞用户。

    Args:
        feedback: 用户当前轮次的反馈文本。
        context: 会话上下文字典，包含 session_id、marker 等字段。
        history: 历史对话消息列表，格式与 get_opencode_history_messages() 返回值相同，
                 每条消息含 role / content / type 字段；传 None 表示无历史。
        llm: LLM 调用对象，需支持 astream 异步流式接口；仅在规则未命中时使用。

    Returns:
        路由决策字典，包含以下字段：
        - target_step (str): 下一步走哪里，取值为
            'text_replace' | 'generation' | 'design' | 'clarify'
        - change_scope (str): 改动范围，取值为
            'text_replace' | 'partial' | 'structural' | 'unclear'
        - reason (str): 分类理由（中文简短描述）
        - confidence (float): 置信度，范围 0~1
        - replacements (list[tuple]): 仅 text_replace 时存在，替换对列表
    """
    # Check for direct text replacement first
    replacements = detect_text_replacement(feedback)
    if replacements:
        return {
            "target_step": "text_replace",
            "change_scope": "text_replace",
            "reason": "文本替换",
            "confidence": 0.99,
            "replacements": replacements,
        }

    # "继续生成" / "ok" etc. — treat as partial re-generation, skip AI classification
    stripped = feedback.strip().rstrip("。！!,.，")
    if stripped in _CONTINUE_SIGNALS_EXACT or any(sig in stripped for sig in _CONTINUE_SIGNALS_CONTAINS):
        return {
            "target_step": "generation",
            "change_scope": "partial",
            "reason": "继续生成指令",
            "confidence": 0.95,
        }

    # Rule-based quick check
    structural_score = sum(1 for s in _STRUCTURAL_SIGNALS if s in feedback)
    partial_score = sum(1 for s in _PARTIAL_SIGNALS if s in feedback)

    if structural_score > partial_score and structural_score > 0:
        return {
            "target_step": "design",
            "change_scope": "structural",
            "reason": "关键词匹配:结构性变更",
            "confidence": 0.9,
        }
    if partial_score > structural_score and partial_score > 0:
        return {
            "target_step": "generation",
            "change_scope": "partial",
            "reason": "关键词匹配:局部调整",
            "confidence": 0.9,
        }

    # AI classification for ambiguous cases
    system_prompt = """判断用户对已生成页面的修改意见属于哪种类型：
- structural: 需要重新设计页面布局/结构（如：加减模块、改布局方式、大范围改动）
- partial: 仅需修改代码细节（如：改颜色、调间距、换文案、小功能调整）
- unclear: 结合对话历史仍无法判断具体要改什么

注意：如果用户当前输入是对前面讨论内容的确认或执行指令（如"好，生成吧"、"就这样"、"按上面说的做"），应结合历史判断修改范围，而不是判为unclear。

只返回JSON: {"change_scope": "structural|partial|unclear", "reason": "简要理由"}"""

    messages: list[dict[str, str]] = []
    for msg in (history or []):
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": feedback})

    try:
        chunks = []
        async for tok in llm.astream(
                [{"role": "system", "content": system_prompt}, *messages],
                temperature=0.0,
        ):
            chunks.append(tok)
        result = json.loads("".join(chunks))
        scope = result.get("change_scope", "partial")
    except json.JSONDecodeError:
        scope = "partial"
        result = {"reason": "默认为局部调整"}
    except Exception:
        # LLM call failed — default to partial to avoid blocking the user
        scope = "partial"
        result = {"reason": "分类服务异常，默认为局部调整"}

    if scope == "unclear":
        return {
            "target_step": "clarify",
            "change_scope": "unclear",
            "reason": result.get("reason", "意图不明确"),
            "confidence": 0.3,
        }

    return {
        "target_step": "design" if scope == "structural" else "generation",
        "change_scope": scope,
        "reason": result.get("reason", ""),
        "confidence": 0.7,
    }
