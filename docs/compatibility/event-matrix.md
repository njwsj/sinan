# SSE 事件兼容性矩阵

## 参考项目

事件采用 `id: <sequence>`、`event: <name>`、`data: <json>`（`page/api/sse.py`），通过 Redis Durable Event Bus 保存并按序号回放（`page/services/generation_event_bus.py:146-179`）。

已确认的事件类别：

| 阶段 | 事件 |
|---|---|
| 生命周期 | `started`、`completed`、`error`、取消错误事件 |
| 生成步骤 | `step`/步骤事件、`analysis_start`、`analysis_end`、`design_start`、`design_end`、`code_start`、`artifact_ready` |
| 交互 | `confirmation_required`、用户确认/拒绝相关事件 |

精确事件名、字段和顺序必须从一次真实生成的完整 SSE 原文确认；源码中的不同 runtime/模板分支可能产生不同序列。

## 当前 sinan

`sinan/services/generation_event_bus.py:25-29` 的事件只有 `type` 和 `data`，不含 id/sequence。

当前 runner 可能发布：

```text
analyze → design → code → [fix → verify] → done
失败：error
```

Coder 还可能发布 `code_delta`（`sinan/agents/coder.py:72`）。事件通过单进程 `asyncio.Queue`，队列在 sentinel 后清理（`generation_event_bus.py:51-63`）。

## 已确认差异

- 无事件 ID、序列号、Last-Event-ID 断线回放。
- 事件仅存在内存，服务重启即丢失。
- 当前 POST 与 SSE 分离；参考 POST 本身建立 SSE。
- 当前事件字段和参考事件名未形成稳定公共契约。
