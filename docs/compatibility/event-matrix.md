# SSE 事件兼容性矩阵

## 参考项目

事件采用 `id: <seq>`、`event: <name>`、`data: <json>`（`page/api/sse.py:21-27`），通过 Redis List 持久化并按序号回放（`page/services/generation_event_bus.py:146-185`）。

- 事件 key：`page:generation:events:{session_id}`；序列号 key：`page:generation:events:seq:{session_id}`（`:12-13`）
- 事件 ID 由 `INCR` 生成，是十进制整数字符串，可直接比较大小（`:61-63`）
- 每条事件的 `data` 内注入 `timeline_seq` 和 `cursor`（`:93-104`）
- 保留上限 1000 条（`LTRIM`），终止事件后 key TTL 120s（`:14-15,152-155`）
- 订阅为 1s 轮询 `LRANGE`，不用 pub/sub（`:171-185`）
- 终止事件集合：`completed`、`error`、`chat`、`awaiting_confirmation`（`:17`）
- 断线续传：`cursor` → `replay` → `subscribe`（`page/api/routes/generate.py:108-125`）
- SSE 心跳 `ping=30`（`page/api/routes/generate.py:78`）
- 取消不是独立事件：`publish_cancelled` 发的是 `event="error"`（`:193-200`）

精确事件名、字段和顺序仍需从一次真实生成的完整 SSE 原文确认；不同 runtime/模板分支可能产生不同序列。

## 当前 sinan（Step 5 后）

与参考同构：Redis List + INCR 序列号，另提供接口一致的内存 fallback。

- 事件模型：`sinan/models/events.py` 的 `GenerationEvent`（`event_id` / `event` / `session_id` / `job_id` / `marker` / `timestamp` / `data`）
  - `to_record()` / `from_record()` 负责 Redis 持久化编解码，损坏记录跳过不抛异常
  - `to_sse()` 产出 `id` / `event` / `data` 三字段，`data` 内注入 `session_id`、`marker`、`job_id`、`timestamp`、`timeline_seq`、`cursor`，`ensure_ascii=True`
  - `TERMINAL_EVENTS` 与 `is_terminal` 定义终止语义
- 事件总线：`sinan/services/generation_event_bus.py`
  - key 前缀 `sinan:generation:events`，序列号 key `sinan:generation:events:seq`
  - 接口：`publish` / `replay` / `subscribe` / `get_last_event_id` / `close` / `trim`
  - `RedisEventBus`（生产）与 `InMemoryEventBus`（`EVENT_BUS_BACKEND=memory`，本地开发）方法签名一致，由 `_build_bus()` 按配置选择
  - `publish` 保留 `(session_id, event_type, data, *, job_id, marker)` 三参数形态，返回 `event_id`
- Redis 连接池：`sinan/services/redis.py` 的 `create_redis` / `get_redis` / `close_redis`，`get_redis` 委托 `create_redis` 保证单一入口；启动时在 `sinan/api/app.py` lifespan 显式创建，关闭时先停 supervisor 再关 Redis
- 订阅入口：`POST /api/page/generate` 与 `GET /api/page/generate/{session_id}/stream`，均支持 `Last-Event-ID` 头与 `cursor` query（头优先，`_resolve_cursor`）
- 终止事件集合：`completed`、`error`、`cancelled`、`chat`、`awaiting_confirmation`
- 保留上限与 TTL 由 `settings.sse_max_events`（1000）/ `sse_terminal_ttl_seconds`（120）控制，轮询间隔 `sse_poll_seconds`（1.0），心跳 `sse_ping_seconds`（30）

## 事件契约

| 事件 | data 字段 | 持久化 | 可回放 | 终止 SSE | Session 状态 | 发布点 |
|---|---|---|---|---|---|---|
| `session_init` | session_id, marker, resume_cursor | 是 | 是 | 否 | 否 | `api/routes/generate.py` |
| `step` | step, message, agent | 是 | 是 | 否 | 否 | `services/generation_runner.py` |
| `analysis_delta` | delta, accumulated_len | 是 | 是 | 否 | 否 | `agents/analyzer.py` |
| `analysis_result` | content | 是 | 是 | 否 | 否 | `agents/analyzer.py` |
| `design_delta` | delta, accumulated_len | 是 | 是 | 否 | 否 | `agents/designer.py` |
| `design_result` | content | 是 | 是 | 否 | 否 | `agents/designer.py` |
| `code_start` | phase, round | 是 | 是 | 否 | 否 | `agents/coder.py` |
| `code_delta` | delta, accumulated_len, phase | 是 | 是 | 否 | 否 | `agents/coder.py` |
| `code_stream_end` | phase, accumulated_len, round | 是 | 是 | 否 | 否 | `agents/coder.py` |
| `verify_result` | passed, quality_score, issues, round, message | 是 | 是 | 否 | 否 | `services/generation_runner.py` |
| `fix_start` | round, strategy, issue_count | 是 | 是 | 否 | 否 | `agents/fixer.py`（Step 7 起） |
| `fix_applied` | round, strategy, fixed_count | 是 | 是 | 否 | 否 | `agents/fixer.py`（Step 7 起，原在 runner） |
| `awaiting_confirmation` | message, confirmation_digest, requirement_doc | 是 | 是 | 是 | → PAUSED | `services/generation_runner.py`（Step 7 起） |
| `completed` | version, preview_url, quality_score, message | 是 | 是 | 是 | → COMPLETED | `services/generation_runner.py` |
| `error` | message, code | 是 | 是 | 是 | → FAILED | `services/generation_runner.py` |
| `cancelled` | message | 是 | 是 | 是 | → FAILED（Step 6 换 CANCELLED） | `services/generation_runner.py` |

已定义常量与 data 构造器、但仍无发布点的事件：`code_snapshot`、`verify_start`（Step 15 补），`chat`（Step 8），`skill_running`、`skill_result`、`knowledge_source`（Step 12）。`gate_passed` 见下方说明。

## Step 7 变更

- **`step` 事件的 `step` / `agent` 取值变了**（前端需同步）：由 `analyze / design / code / verify / fix`
  改为 `router / analyst / designer / coder / verifier / fixer`，与参考节点名一致
  （`services/generation_runner.py` 的 `step_labels`）。按 `step` 值做 UI 分支的地方会失配。
- `completed.quality_score` 与 `verify_result.quality_score` 自 Step 7 起为真值，由
  `models/contracts.compute_quality_score(issues)` 计算：P0=0.30 / P1=0.10 / P2=0.02 累加，
  `round(1 - penalty, 2)`，下限 0.0。`verify_result.issues` 是 `ValidationIssue.model_dump()`
  列表（issue_id / severity / category / description / location / suggestion）。
- `fix_start` / `fix_applied` 的发布点改为 `agents/fixer.py`，每轮修复各发一条。
  **这是 sinan 增量**：参考的 native pipeline（`page/agents/fixer.py`）不发任何事件，
  这两个事件只在 claude_code / opencode 运行时里发（`page/claude_code/codegen_engine.py:1240,1250`）。
  原先 runner 在图跑完后补发的那条 `fix_applied` 已移除，避免重复。
  另注：`fix_applied.fixed_count` 实际传的是"本轮修复前的问题数"，不是真正修好的数量（参考亦无真实计数）。
- `awaiting_confirmation` 自 Step 7 起有发布点，payload 为 `{message, confirmation_digest, requirement_doc}`，
  同时 Session 落 `paused` + `pipeline_state=user_confirm`，Job 落 `waiting`。
- `gate_passed` 仍无发布点：参考不发 gate 事件，门禁报告只落 `gen_session.gate_reports`（Text 列，JSON 文本）。sinan 保持一致，不擅自新增事件。

## 已对齐

- 事件 ID 为递增整数，`Last-Event-ID` 与 `cursor` 均可续传；`replay` 按 `seq > cursor` 过滤，不丢不重
- 事件持久化在 Redis List，服务重启后仍可回放
- 终止事件只关闭当前 SSE 连接，key 带 TTL 存活，任务结束后再连接仍能收到 `completed`
- 多客户端各自持有游标，互不消费对方事件（旧 `asyncio.Queue` 是消费型的，两个客户端会互抢事件，该缺陷已消除）
- POST 入口本身即建立 SSE，`ping=30`，`data` 用 `ensure_ascii=True` 规避代理对
- 事件名与 data 字段集中在 `sinan/models/events.py`，形成稳定公共契约

## 未对齐（待后续 Step 或待黑盒确认）

- 取消事件名不同：参考用 `event="error"` 承载取消，sinan 用独立的 `cancelled`。需按前端实际契约二选一。
- `session_init.resume_cursor` 当前恒为空字符串（真实游标通过 `data.cursor` 下发，`event_id` 记在服务端日志）。该字段是否保留待前端确认。
- 参考侧 `started`、`analysis_start`、`analysis_end`、`design_start`、`design_end`、`artifact_ready` 等事件名尚未逐一核对，需从一次真实生成的完整 SSE 原文确认后再决定是否与 sinan 的 `step` 合并。
- `code_delta` 逐 token 落 Redis（INCR + RPUSH + LTRIM），与参考同构但 QPS 放大明显。若压测出现瓶颈，优化方向是在 coder 侧按字符数或时间窗聚合 delta，而不是绕过持久化。
- `analysis_delta` / `design_delta` 是 sinan 的流式增量（参考 analyst/designer 用非流式 `ainvoke`，只有最终文本）。事件协议自 Step 5 固化，不回退，但对照时参考侧不会有这两类事件。
- `verify_result.issues` 的条目数与内容取决于是否开启渲染校验：`render_validation_enabled` 默认 False，且 sinan 未接 Vision LLM 视觉检查（参考 `page/harness/validators/render.py` 有 28 项视觉检查）。因此 sinan 侧 issue 更少、修复轮数更少、`quality_score` 系统性偏高。Step 15 对照前必须先统一这两项。
- 事件完整顺序尚未做双项目对照回归（Step 15）。
