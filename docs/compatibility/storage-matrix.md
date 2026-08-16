# 持久化与存储兼容性矩阵

| 对象 | 参考项目 | 当前 sinan | 差异 |
|---|---|---|---|
| Session | `GenerationSession`，含用户、状态、步骤、需求、marker 等 | `gen_session`，`sinan/models/tables.py:8-37` | 字段/状态不同 |
| Job | `GenerationJob`，MySQL 持久化、租约和重连复用 | `generation_job`（Step 4 方案），MySQL 持久化、原子租约、`create_or_get_job` 复用 | 结构已对齐；status 用字符串常量，无 title/messages 等 Session 专属列 |
| 步骤 | session 消息/审计及运行时记录 | `gen_session_step`，`tables.py:40-61` | 事件与存储未统一 |
| Page | 参考 `Page` | 无独立 Page ORM | 缺失 |
| PageVersion | 参考版本快照，BOS 存储 | `page_version`，HTML/source_code 直接入库 | 存储介质和发布元数据不同 |
| Artifact | 参考 `GenerationArtifact`，支持类型和内容读取 | 无 Artifact 表 | 缺失 |
| 上传附件 | 参考上传服务、对象存储/数据元信息 | 本地 JSON，runner 从 `attachment_storage_path` hydrate | 仅覆盖部分 Excel/数据路径 |
| 事件 | Redis stream/list，带 seq | 内存 `asyncio.Queue` | 无持久化/回放 |
| Runtime checkpoint | LangGraph/runtime checkpoint | 当前由 graph 配置 thread_id，但未形成对外恢复协议 | 待验证 |

当前页面保存路径：`sinan/services/page_store.py:16-31`；完成时由 runner 更新 Session 的 `marker/version/preview_url`（`generation_runner.py:129-147`）。
