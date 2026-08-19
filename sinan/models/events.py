# sinan/models/events.py
"""生成事件协议：事件模型、事件名常量、事件构造器。

对齐参考项目 page/api/sse.py + page/services/generation_event_bus.py：
- SSE 线上格式为 id / event / data 三行，data 是 JSON 字符串；
- data 内固定注入 timeline_seq 和 cursor，供客户端断线重连；
- 终止事件只关闭当前 SSE 连接，不影响历史回放。

文件职责划分：
- 本文件只管数据结构，不碰 Redis 和网络；
- generation_event_bus.py 负责把事件存入 / 读出 Redis；
- generate.py 路由负责把事件发给 SSE 客户端。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 事件名常量
# 其他文件用 events.COMPLETED 而不是裸字符串 "completed"，
# 改名时只改这里一处，不会漏改。
# ---------------------------------------------------------------------------
SESSION_INIT = "session_init"       # 会话建立，客户端拿到初始游标
STEP = "step"                       # 流水线节点开始（analyze / design / code …）
GATE_PASSED = "gate_passed"         # 质量门通过
CODE_START = "code_start"           # 代码生成开始
CODE_DELTA = "code_delta"           # 代码 token 增量（流式）
CODE_SNAPSHOT = "code_snapshot"     # 当前完整代码快照
CODE_STREAM_END = "code_stream_end" # 代码 token 流结束
VERIFY_START = "verify_start"       # 验证开始
VERIFY_RESULT = "verify_result"     # 验证结果（passed / issues / score）
FIX_START = "fix_start"             # 自动修复轮次开始
FIX_APPLIED = "fix_applied"         # 修复轮次完成
ANALYSIS_DELTA = "analysis_delta"   # 需求分析 token 增量（流式）
ANALYSIS_RESULT = "analysis_result" # 需求分析完成（流结束）
DESIGN_DELTA = "design_delta"       # 设计方案 token 增量（流式）
DESIGN_RESULT = "design_result"     # 设计方案完成（流结束）
SKILL_RUNNING = "skill_running"     # Skill 执行中（Step 12 实现）
SKILL_RESULT = "skill_result"       # Skill 执行结果（Step 12 实现）
KNOWLEDGE_SOURCE = "knowledge_source"           # 知识库摄取（Step 12 实现）
AWAITING_CONFIRMATION = "awaiting_confirmation" # 等待用户确认（终止当前 SSE）
CHAT = "chat"                       # 纯聊天回复，不触发生成（终止当前 SSE）
COMPLETED = "completed"             # 生成完成（终止当前 SSE）
ERROR = "error"                     # 生成失败（终止当前 SSE）
CANCELLED = "cancelled"             # 用户取消（终止当前 SSE）

# 收到这些事件后，SSE 订阅者应关闭当前连接。
# 注意：关闭的是"这次连接"，事件仍留在 Redis 里（带 TTL），
# 断线重连后携带 Last-Event-ID 仍能回放这些事件。
# 参考：page/services/generation_event_bus.py:17
# 差异：sinan 额外包含 cancelled（参考用 error 事件承载取消）
TERMINAL_EVENTS: frozenset[str] = frozenset(
    {COMPLETED, ERROR, CANCELLED, CHAT, AWAITING_CONFIRMATION}
)


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串，精确到毫秒。"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class GenerationEvent(BaseModel):
    """一条持久化的生成事件。

    event_id 即 Redis INCR 生成的 timeline 序列号（十进制字符串），
    客户端用它做 Last-Event-ID / cursor 实现断线续传。

    数据流向：
        publish()  →  GenerationEvent(...)  →  to_record()  →  RPUSH Redis
        LRANGE Redis  →  from_record()  →  GenerationEvent  →  to_sse()  →  SSE 客户端
    """

    event_id: str                                           # 序列号，"1" "2" "3" …
    event: str                                              # 事件名，对应上方常量
    session_id: str                                         # 归属 session
    job_id: str | None = None                               # 归属 job（可选）
    marker: str | None = None                               # 归属页面 marker（可选）
    timestamp: str = Field(default_factory=_now_iso)        # 发布时间，自动填 UTC ISO
    data: dict[str, Any] = Field(default_factory=dict)      # 业务 payload

    # ---- 持久化编解码 ----

    def to_record(self) -> str:
        """序列化为写入 Redis List 的字符串。

        格式：{"seq": 5, "event": {完整 GenerationEvent 字段}}
        seq 冗余存一份是为了 from_record 解析时不依赖外部游标。
        调用方（RedisEventBus.publish）拿到这个字符串后执行 RPUSH。
        """
        return json.dumps(
            {"seq": int(self.event_id or 0), "event": self.model_dump()},
            ensure_ascii=False,
        )

    @classmethod
    def from_record(cls, raw: str) -> "GenerationEvent | None":
        """从 Redis List 读出的原始字符串反序列化回 GenerationEvent。

        解析失败返回 None 而不抛异常，bus 层跳过损坏记录继续处理后续事件。
        兼容两种格式：
          - 新格式：{"seq": N, "event": {...}}  （to_record 写入的）
          - 旧格式：直接是 GenerationEvent 的字段 dict
        """
        try:
            record = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(record, dict):
            return None
        # 新格式取 "event" 子键，旧格式整体就是 payload
        payload = record.get("event") if "seq" in record else record
        if not isinstance(payload, dict):
            return None
        try:
            return cls.model_validate(payload)
        except Exception:
            return None

    # ---- SSE 线上格式 ----

    def to_sse(self) -> dict[str, str]:
        """转换为 sse_starlette EventSourceResponse 需要的三字段 dict。

        输出格式（对应 HTTP 文本）：
            id: 5
            event: step
            data: {"step": "analyze", ..., "timeline_seq": 5, "cursor": "5"}

        data 里额外注入：
          - timeline_seq：整数序列号，客户端可直接比较大小
          - cursor：与 event_id 相同的字符串，客户端断线后放进 Last-Event-ID

        session_id / marker / job_id 按需注入，避免客户端每次都要额外查询。
        ensure_ascii=True 规避代理对（surrogate codepoint）污染 SSE 文本流。
        """
        data = dict(self.data)
        data.setdefault("session_id", self.session_id)
        if self.marker is not None:
            data.setdefault("marker", self.marker)
        if self.job_id is not None:
            data.setdefault("job_id", self.job_id)
        data["timestamp"] = self.timestamp
        data["timeline_seq"] = int(self.event_id or 0)
        data["cursor"] = self.event_id
        return {
            "id": self.event_id,
            "event": self.event,
            "data": json.dumps(data, ensure_ascii=True),
        }

    @property
    def is_terminal(self) -> bool:
        """是否是终止事件（收到后 SSE 订阅者应关闭连接）。"""
        return self.event in TERMINAL_EVENTS


# ---------------------------------------------------------------------------
# 事件 data 构造器
# 每个函数对应一种事件的 data 字段，集中约束字段名和类型，
# 避免各调用点手写 dict 导致字段名拼错或漏字段。
# 调用示例：event_bus.publish(session_id, events.STEP, events.step_data("analyze", "分析中"))
# ---------------------------------------------------------------------------

def session_init_data(session_id: str, marker: str, cursor: str) -> dict:
    """会话建立事件。resume_cursor 是当前最新游标，客户端可用于断线续传。"""
    return {"session_id": session_id, "marker": marker, "resume_cursor": cursor}


def step_data(step: str, message: str, agent: str | None = None) -> dict:
    """流水线节点进入事件。agent 标识执行该节点的 agent 名称（可选）。"""
    d = {"step": step, "message": message}
    if agent:
        d["agent"] = agent
    return d


def gate_passed_data(gate: str, step: str, score: float) -> dict:
    """质量门通过事件。score 为 0~1 的质量分。"""
    return {"gate": gate, "step": step, "score": score}


def code_start_data(phase: str = "coding", round_num: int | None = None) -> dict:
    """代码生成开始事件。phase 区分首次生成（coding）和修复轮次（fix）。"""
    d = {"phase": phase}
    if round_num is not None:
        d["round"] = round_num
    return d


def code_delta_data(delta: str, accumulated_len: int, phase: str = "coding") -> dict:
    """代码 token 增量事件。accumulated_len 是截至本 token 的累计字符数。"""
    return {"delta": delta, "accumulated_len": accumulated_len, "phase": phase}


def code_stream_end_data(accumulated_len: int, phase: str = "coding",
                         round_num: int | None = None) -> dict:
    """代码 token 流结束事件。accumulated_len 是本轮代码的总字符数。"""
    d = {"phase": phase, "accumulated_len": accumulated_len}
    if round_num is not None:
        d["round"] = round_num
    return d


def verify_start_data(round_num: int) -> dict:
    """验证开始事件。round_num 从 0 起，对应第几轮修复后的验证。"""
    return {"round": round_num}


def verify_result_data(passed: bool, quality_score: float,
                       issues: list, round_num: int) -> dict:
    """验证结果事件。

    Step 7 起 quality_score 为真值，由 models/contracts.compute_quality_score(issues)
    计算（P0=0.30 / P1=0.10 / P2=0.02 累加，下限 0.0）；
    issues 是 ValidationIssue.model_dump() 列表。
    """
    return {"passed": passed, "quality_score": quality_score,
            "issues": issues, "round": round_num}


def fix_start_data(round_num: int, strategy: str, issue_count: int) -> dict:
    """自动修复轮次开始事件。strategy 为修复策略名，issue_count 为待修复问题数。"""
    return {"round": round_num, "strategy": strategy, "issue_count": issue_count}


def fix_applied_data(round_num: int, strategy: str, fixed_count: int) -> dict:
    """修复轮次完成事件。fixed_count 为本轮实际修复的问题数。"""
    return {"round": round_num, "strategy": strategy, "fixed_count": fixed_count}


def completed_data(version: int, preview_url: str, quality_score: float,
                   features: list | None = None) -> dict:
    """生成完成事件。Step 7 起 quality_score 为真值（见 verify_result_data）。"""
    d = {"version": version, "preview_url": preview_url,
         "quality_score": quality_score, "message": "页面生成完成"}
    if features:
        d["features"] = features
    return d


def error_data(message: str, code: str = "INTERNAL_ERROR") -> dict:
    """生成失败事件。code 为机器可读的错误码，message 为人类可读描述。"""
    return {"message": message, "code": code}


def cancelled_data(message: str = "生成已取消") -> dict:
    """用户取消事件。"""
    return {"message": message}


def analysis_result_data(content: str) -> dict:
    """需求分析完成事件（流结束）。content 是完整需求分析文本。"""
    return {"content": content}


def design_result_data(content: str) -> dict:
    """设计方案完成事件（流结束）。content 是完整设计方案文本。"""
    return {"content": content}


def analysis_delta_data(delta: str, accumulated_len: int) -> dict:
    """需求分析 token 增量事件。"""
    return {"delta": delta, "accumulated_len": accumulated_len}


def design_delta_data(delta: str, accumulated_len: int) -> dict:
    """设计方案 token 增量事件。"""
    return {"delta": delta, "accumulated_len": accumulated_len}
