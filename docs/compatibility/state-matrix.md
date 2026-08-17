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

参考 Job 由 `GenerationJobStore` 持久化；活动 Job 重连时复用（`page/services/generation_job_store.py:73-99`）。取消、租约、失败和完成的精确边界需要黑盒确认。

## 当前 sinan

`sinan/models/enums.py:13`：

```text
pending → running → completed
pending/running → failed
running → awaiting_input  # 枚举存在，当前 API 没有确认/恢复实现
```

Page 状态（`sinan/models/enums.py:26`）：

```text
draft → published → archived
```

Session 持久化字段位于 `sinan/models/tables.py:8-37`。

Step 4 起新增独立 `GenerationJob`（`sinan/models/tables.py`，字符串 status 列），任务状态流转：

```text
pending → running → completed
pending/running → failed
pending/running → cancelled     # mark_cancelled
running(租约过期) → running      # 重新领取，attempts+1，直至 max_attempts
```

由 `GenerationJobStore` 原子租约（`try_claim_job`）+ `generation_supervisor` 周期恢复驱动。

## 兼容判定

| 状态能力 | 参考 | 当前 | 结论 |
|---|---|---|---|
| 持久化 Session | 是 | 是 | 字段和枚举不同 |
| 独立 Job | 是 | 是（Step 4 方案） | 已对齐结构；job status 用字符串常量 |
| 取消/abort | 是 | 部分（Step 4 方案） | 已引入 Redis `cancel_registry`（内存 Event+Redis 键），运行中可在**节点边界**打断；`request_cancel`+finalize 复查保证 cancel 后不置 completed。单节点内的即时打断粒度、事件顺序待黑盒验证 |
| resume/reconnect | 是 | 部分（Step 4 + Step 5） | 进程重启后 lease 过期→supervisor 重新领取可恢复；SSE 事件已落 Redis List，携带 `Last-Event-ID`/`cursor` 可回放（Step 5） |
| confirm/reject | 是 | 否 | 缺失（Step 8） |
| 二次 iterate | 是 | 否 | 缺失（Step 8） |
| 页面版本状态 | Page/PageVersion | 单一 PageVersion 表 | 结构与发布语义需继续对齐 |

> 说明：上表"当前"列中标注"Step 4 方案"的项为本 Step 设计目标，代码落地后需按验收标准做黑盒验证方可确认兼容。
