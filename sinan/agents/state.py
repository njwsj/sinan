# sinan/agents/state.py
"""LangGraph 节点之间共享的流水线状态。键名与参考 page/agents/state.py 1:1。

旧键映射：prompt→user_input，requirements→requirement_doc + analysis_output，
design→design_doc，html→code(+code_hash/code_files)，
verified/verify_message→verification_result，iteration→fix_round，
max_iterations→max_fix_rounds，gate_decision→gate_reports（列表，每条含 decision）。
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class GenerationState(TypedDict, total=False):
    # ---- 会话身份 ----
    session_id: str          # 同时是 LangGraph thread_id
    job_id: str
    marker: str
    user_id: str

    # ---- 用户输入 ----
    user_input: str
    attachments: list        # hydrate 后，每项含 parsed: {columns, rows, row_count}
    datasources: list

    # ---- agent 产出 ----
    intent: dict | None              # router: {intent, confidence, extracted_info}
    requirement_doc: str | None      # analyst: 确认摘要（挂起时是完整 markdown）
    analysis_output: dict | None     # analyst: {_format,_content,confidence_score,confirmation_digest}
    design_doc: dict | None          # designer: {_format,_content,layout,component_tree,style_tokens}
    code: str | None
    code_files: list[dict]           # [{path,content,language,role}]，当前恒 1 个 index.html
    code_hash: str | None
    features: list

    # ---- Harness 控制 ----
    pipeline_state: str
    status: Literal[
        "routing", "analyzing", "designing", "coding", "verifying", "fixing",
        "awaiting_confirmation", "completed", "failed", "completed_with_warnings",
    ]
    gate_reports: list[dict]
    contract_errors: list[dict]
    verification_result: dict | None

    # ---- 修复循环 ----
    fix_round: int
    max_fix_rounds: int
    fix_history: list[dict]
    repair_strategy: str

    # ---- 多轮（Step 8 起真正使用）----
    messages: Annotated[list[AnyMessage], add_messages]
    history_messages: list[dict]
    user_confirmed: bool | None
    iteration_feedback: str | None

    # ---- 模板（Step 11）----
    template_id: str | None
    template_code: str | None

    # ---- Skill / 知识库 / 数据源（Step 12 起真正使用）----
    skill_keys: list[str]  # 请求显式指定的 skill_key（强制选择）
    selected_skills: list[dict]  # 本次实际选中的 Skill（含来源 explicit/routed）
    skill_results: list[dict]  # 每个 Skill 的归一化结果，追加写
    skill_result: str | None  # 最近一次成功 Skill 的正文（对齐参考同名键）
    skill_link_required: bool | None  # True 表示因缺链接挂起，图在 skill 节点后 END
    skill_context: dict | None  # {selected, results, ok_count, failed}

    knowledge_sources: list[str]  # 待摄取的本地路径 / URL
    knowledge_context: dict | None  # {items: [...], ok_count, chars}
    external_knowledge: str | None  # 合并清洗后注入 prompt 的知识正文
    external_knowledge_loaded: bool | None  # 防止 confirm/iterate 续跑时重复抓取

    datasource_context: dict | None  # data_service.resolve_datasources() 的结果

    force_auto_confirm: bool | None