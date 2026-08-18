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

当前实际写入点只有四处：`session_store.create()` 写 `init`，runner 启动写 `analysis`，成功写 `delivered`，失败/取消写 `failed`。中间阶段（ingestion/user_confirm/design/generation/validation/preview/user_review）尚未推进，属于 Step 7/8。

任务状态 `JobStatus`（`enums.py:50`）：

```text
pending → running → completed
pending/running → failed
pending/running → cancelled     # mark_cancelled
running → waiting → running     # 等待用户确认，枚举已就位，发布点属于 Step 8
running(租约过期) → running      # 重新领取，attempts+1，直至 max_attempts
```

由 `GenerationJobStore` 原子租约（`claim_job`）+ `generation_supervisor` 周期恢复驱动。
注意 `generation_job_store.py` 仍使用模块级裸字符串常量（`PENDING`/`RUNNING`/`CANCELLED`），
与 `JobStatus` 取值一致但未收敛到同一处定义。

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
| 流水线阶段 | 11 态 PipelineState | 枚举齐全，仅 init/analysis/delivered/failed 有写入点 | 结构对齐，阶段推进待 Step 7/8 |
| 独立 Job | 是 | 是 | 已对齐；`waiting` 无发布点，常量未收敛到 `JobStatus` |
| 取消/abort | 是（error 事件承载） | 部分 | 运行中可在**节点边界**打断；Session 落 `failed` + `error_message="cancelled by user"`。参考无 cancelled 会话态，语义等价性待 Step 15 黑盒确认 |
| resume/reconnect | 是 | 部分 | lease 过期→supervisor 重新领取可恢复；SSE 事件落 Redis List，带 `Last-Event-ID`/`cursor` 可回放（Step 5） |
| confirm/reject | 是 | 否 | 枚举已备（`paused`/`waiting`/`user_confirm`），行为缺失（Step 8） |
| 二次 iterate | 是 | 否 | 缺失（Step 8） |
| 页面版本状态 | Page 主表 + 不可变 PageVersion | 同结构（Step 6） | 已对齐；发布链路（published_to/BOS）待 Step 9/10 |

> 说明：Step 6 只完成模型与枚举层面的结构对齐，所有"已对齐"结论仍需在 Step 15 用黑盒测试与参考项目做同输入对照后才能确认。
