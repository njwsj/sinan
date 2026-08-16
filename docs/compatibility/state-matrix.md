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

Session 持久化字段位于 `sinan/models/tables.py:8-37`；没有独立 GenerationJob 表。

## 兼容判定

| 状态能力 | 参考 | 当前 | 结论 |
|---|---|---|---|
| 持久化 Session | 是 | 是 | 字段和枚举不同 |
| 独立 Job | 是 | 否 | 不兼容 |
| 取消/abort | 是 | 否 | 缺失 |
| resume/reconnect | 是 | 仅内存队列消费 | 进程重启或消费后重连失败 |
| confirm/reject | 是 | 否 | 缺失 |
| 二次 iterate | 是 | 否 | 缺失 |
| 页面版本状态 | Page/PageVersion | 单一 PageVersion 表 | 结构与发布语义需继续对齐 |
