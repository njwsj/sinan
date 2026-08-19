# 状态与转移矩阵

## 参考项目

参考 `SessionStatus`（`page/models/enums.py:33`）：

```text
active → paused
active → completed
active → failed
paused → active       # resume
active/paused → archived
```

参考 `PipelineState`（`page/models/enums.py:6`）为 11 态：init / ingestion / analysis / user_confirm /
design / generation / validation / preview / user_review / delivered / failed。

参考 Job 由 `GenerationJobStore` 持久化；活动 Job 重连时复用（`page/services/generation_job_store.py:73-99`）。取消、租约、失败和完成的精确边界需要黑盒确认。

## 当前 sinan

Step 6 起枚举取值与参考对齐（`sinan/models/enums.py`），且所有 status 列改为 `String(32)`，不再使用数据库 ENUM。
本 Step 通过新建空库 `sinan_v2` 落地，因此不存在旧状态值的存量数据。

会话状态 `SessionStatus`（`enums.py:31`）：

```text
active → paused          # 等待用户确认/补充（Step 8 使用）
paused → active          # resume
active → completed / failed
active/paused → archived
```

与旧库取值的语义对应：`pending`/`running` → `active`，`awaiting_input` → `paused`。

流水线阶段 `PipelineState`（`enums.py:11`，新增 `gen_session.pipeline_state` 列，取值与参考 11 态一致）：

```text
init → ingestion → analysis → user_confirm → design
     → generation → validation → preview → user_review → delivered
任意阶段 → failed
```

Step 7 起写入点扩展到 9 个阶段：

- `session_store.create()` 写 `init`；runner 启动也写 `init`（`generation_runner.py:52-56`，Step 6 时写的是 `analysis`）；
- `harness/orchestrator.py:_persist()` 在每个节点执行后写：`ingestion`(router) / `analysis`(analyst) / `design`(designer) / `generation`(coder、fixer) / `validation`(verifier)；
- analyst 低置信度挂起时写 `user_confirm`（`agents/analyzer.py:165` + runner 挂起分支）；
- runner 成功写 `delivered`，失败/取消写 `failed`。

仍无写入点的两个阶段是 `preview` 和 `user_review`。参考项目同样没有 PREVIEW / USER_REVIEW 节点（`page/agents/graph.py` 只有 6 个节点，`gates._gate_render_success` 自注释为 placeholder），属于**两边共同缺口**，不是 sinan 差异。

> sinan 增量：`user_confirm` 这个取值。参考 `page/agents/analyst.py:245`/`:252` 两个分支都写 `pipeline_state="analysis"`，挂起状态只体现在 `status="awaiting_confirmation"` 上。sinan 选择在节点与 Session 行上都写 `user_confirm`，语义更明确，但 Step 15 逐字段对照时 `pipeline_state` 会不一致，需按此说明豁免。

任务状态 `JobStatus`（`enums.py:50`）：

```text
pending → running → completed
pending/running → failed
pending/running → cancelled     # mark_cancelled
running → waiting               # Step 7 起有发布点：mark_waiting（analyst 低置信度挂起）
waiting → running               # 恢复执行属 Step 8
running(租约过期) → running      # 重新领取，attempts+1，直至 max_attempts
```

由 `GenerationJobStore` 原子租约（`claim_job`）+ `generation_supervisor` 周期恢复驱动。
状态常量已收敛到 `JobStatus`（`generation_job_store.py:13-18`）。

`mark_waiting()`（`:170`）清空 `lease_owner`，因此 `run_job` 随后的 `mark_completed`
（where `lease_owner == owner`）命中 0 行，挂起的 Job 不会被误置 completed。
注意 `ACTIVE_STATUSES = {pending, running}` 不含 `waiting`，所以挂起 Job 不会被
supervisor 重新领取、也不会被 `create_or_get_job` 复用——用户重新发起会新建 Job。
该语义是否合适待 Step 8 的确认接口落地后复核。

页面状态 `PageStatus`（`enums.py:66`，现由 `page` 主表承载，`page_version` 已无 status 列）：

```text
draft → preview → published → archived
```

实际写入：`page_store.save()` 首次建页写 `preview`，`publish()` 写 `published`；`draft`/`archived` 暂无写入点。

`PageSource`（generation/manual/template）已定义，无使用点（Step 10/11）。

## 兼容判定

| 状态能力 | 参考 | 当前 | 结论 |
|---|---|---|---|
| 持久化 Session | 是 | 是 | 枚举取值与主要字段已对齐（Step 6） |
| 流水线阶段 | 11 态 PipelineState，实际写入 9 态 | 同为 9 态有写入点（Step 7） | 已对齐；`preview`/`user_review` 参考亦无节点，共同缺口。`user_confirm` 取值为 sinan 增量 |
| 独立 Job | 是 | 是 | 已对齐；`waiting` 自 Step 7 起有发布点（`mark_waiting`），常量已收敛到 `JobStatus` |
| 取消/abort | 是（error 事件承载） | 部分 | 运行中可在**节点边界**打断；Session 落 `failed` + `error_message="cancelled by user"`。参考无 cancelled 会话态，语义等价性待 Step 15 黑盒确认 |
| resume/reconnect | 是 | 部分 | lease 过期→supervisor 重新领取可恢复；SSE 事件落 Redis List，带 `Last-Event-ID`/`cursor` 可回放（Step 5） |
| confirm/reject | 是 | 部分 | Step 7：analyst 置信度 < `auto_confirm_threshold`(0.3) 时图在 analyst 后终止，Session 落 `paused` + `user_confirm`，Job 落 `waiting`，发 `awaiting_confirmation` 事件；确认/拒绝接口与恢复执行属 Step 8 |
| 二次 iterate | 是 | 否 | 缺失（Step 8）；state 已有 `iteration_feedback` / `history_messages` 占位 |
| 页面版本状态 | Page 主表 + 不可变 PageVersion | 同结构（Step 6） | 已对齐；发布链路（published_to/BOS）待 Step 9/10 |
| 门禁报告 | 6 个门（schema_validation / user_confirmation / design_completeness / syntax_integrity / quality_threshold / render_success） | 同 6 个门（Step 7） | 门名、阈值、分派表已对齐；报告额外带 `decision`/`issues`/`timestamp` 三个字段，参考只有 `gate/step/passed/score/auto_confirmed/requires_user`（`page/harness/orchestrator.py:119-126`），属 sinan 增量 |
| 契约校验 | 5 个步骤输出契约，违规只记录不阻断 | 同 5 个（Step 7），写入 `state["contract_errors"]` | 已对齐。注意 ANALYSIS（缺 `functional_modules`）与 VALIDATION（缺 `total_rounds`）两个契约在**两边都稳定失败**，因为 analyst/verifier 实际产出结构与契约不符——参考既有行为，不要"修好" |
| 状态机运行时校验 | 定义了 `PipelineStateMachine` 但全仓无 import | 同结构 11 态带条件转移表，同样未接入运行时 | 实施计划 7.5 的"唯一状态转移来源"参考侧也未达成，属两边共同缺口，留 Step 15 |

> 说明：Step 6 只完成模型与枚举层面的结构对齐，所有"已对齐"结论仍需在 Step 15 用黑盒测试与参考项目做同输入对照后才能确认。

## Step 7 补充：流水线状态由谁写

`harness/state_machine.py` 已改为与参考 1:1 的 11 态带条件转移表（14 条转移，带
`user_confirmed` / `repair_needed` / `change_structural` 等条件），但**运行时并未接入**：
`pipeline_state` 仍由各节点直接返回字符串，`orchestrator._persist()` 落库。
参考项目的 `PipelineStateMachine` 同样零调用点，因此这是两边共同的缺口。

图的实际走向由两个条件函数决定（`agents/graph.py`）：

- `_after_analyst`：`user_confirmed is None and status == "awaiting_confirmation"` → END，否则 designer；
- `_should_fix`：`verification_result.passed` → complete；`fix_round >= max_fix_rounds` → complete_with_warnings；否则 fixer。

已知行为：`complete_with_warnings` 出口的 `verification_result.passed` 仍是 False，
runner 因此抛 `ValueError` → Job `failed`、Session `failed`。参考的 native 路径同为此行为。
若要让"修满 3 轮仍有 P1 也算交付"，需同时改 runner 收尾判断与 `completed` 事件语义，属行为增量，不在 Step 7 范围。
