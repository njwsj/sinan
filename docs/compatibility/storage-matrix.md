# 持久化与存储兼容性矩阵

> 库隔离说明（Step 6 起）：本分支连接独立新库 `sinan_v2`，Redis 用 `db 1`
> （`sinan/config/settings.py:15,20`）。Step 5 及之前的分支继续使用 `sinan` / `db 0`。
> 库名写在 `settings.py` 而不是 `.env`，因为 `.env` 被 gitignore、为所有分支共用，
> 写进 `.env` 会导致切回旧分支时旧代码也连到新库。

| 对象 | 参考项目 | 当前 sinan | 差异 |
|---|---|---|---|
| Session | `GenerationSession`，含用户、状态、步骤、需求、marker、messages/attachments、逻辑删除 | `gen_session`（Step 6 重建，`tables.py:20`），新增 `pipeline_state`/`title`/`requirement_doc`/`messages`/`attachments`/`template_id`/`fix_rounds`/`verification_score`/`gate_reports`/`model_versions`/`is_deleted` 三列 | 字段已对齐；status 取值改为 active/paused/completed/failed/archived；sinan 额外保留 `prompt`/`iteration`/`total_tokens` |
| Job | `GenerationJob`，MySQL 持久化、租约和重连复用 | `generation_job`（Step 4，`tables.py:103`），status 默认值取自 `JobStatus`，取值含 `waiting` | 结构已对齐；`waiting` 态尚无发布点（Step 8） |
| 步骤 | session 消息/审计及运行时记录 | `gen_session_step`（`tables.py:75`） | sinan 独有的细粒度审计表，参考侧用 messages + artifact 承载，语义不逐字对齐 |
| Page | 参考 `Page`（marker unique、current_version、published_version、published_to、quality_score） | `page`（Step 6 新增，`tables.py:165`），字段按参考 1:1 建立 | 已对齐；`allowed_datasources`/`cover_url`/`tags`/`description` 暂无写入点 |
| PageVersion | 参考版本快照，正文在 BOS（bos_path/entry_file/file_list/content_hash/security_scan/harness_score/repair_rounds） | `page_version`（Step 6 重建，`tables.py:200`），列位已对齐；正文仍走 `html_content`，`bos_path`/`file_list` 可空；已卸掉 `status`/`owner`/`updated_at` | 存储介质未对齐，待 Step 9 接对象存储后把 `bos_path` 收紧为非空 |
| Artifact | 参考 `GenerationArtifact`，支持类型和内容读取 | `generation_artifact`（Step 6 新增，`tables.py:137`），`metadata` 列以属性名 `meta` 映射（`metadata` 是声明式保留名） | 表已建立，写入点属于 Step 7/9 |
| 上传附件 | 参考上传服务 + `generation_session.attachments` JSON，无独立表 | `attachment`（Step 6 新增，`tables.py:234`，仅建表未切流量）；权威来源仍是本地 JSON + runner 的 `attachment_storage_path` hydrate | 有意不对齐：参考无此表，Step 9 统一存储时再决定归属 |
| Skill / Template | `skill_definition` / `page_template` | 同名表已建（Step 6，`tables.py:256,277`），无读写点 | 结构对齐，行为待 Step 11/12 |
| sys_user / buddy_profile | 参考存在 | 不建表 | 有意不对齐：认证 Step 3 已定"暂不实现"；buddy 与页面生成无关 |
| 事件 | Redis List，带 seq | Redis List + INCR seq（Step 5）：`sinan:generation:events:{sid}`，上限 1000 条，终止事件后 TTL 120s；本分支 `redis_db=1` | 持久化与回放已对齐 |
| 迁移 | 由 DBA/外部管理 | 无迁移体系：开发期靠 `init_db()` 的 `create_all()`；Step 6 的模型升级采用「新建空库 + create_all」，旧库 `sinan` 原样保留 | 未对齐：Alembic 推迟到有真实数据需保留时再引入 |
| Runtime checkpoint | LangGraph/runtime checkpoint | 由 graph 配置 thread_id，未形成对外恢复协议 | 待验证 |

## 写入路径

- 页面：`sinan/services/page_store.py:save()` 在单个事务里 upsert `page` + 插入 `page_version` + 推进 `current_version`，并写 `content_hash`/`code_size`/`file_list`/`harness_score`/`repair_rounds`；发布走 `publish()`（完整链路 Step 10）。
- 会话：`session_store.create()` 落 `status=active` + `pipeline_state=init` + `title`；完成时 runner 回写 `marker`/`version`/`preview_url`/`pipeline_state=delivered`/`fix_rounds`/`verification_score`（`generation_runner.py`）。
- 读取：`page_version` 只提供快照字段，页面级状态（status/current_version/published_version）统一从 `page` 主表读（`api/routes/pages.py`、`api/routes/preview.py`）。

## 遗留项

- `page_version.bos_path`/`file_list` 仍是兼容期取值，正文在 `html_content`（Step 9）；
- `generation_artifact`、`attachment`、`skill_definition`、`page_template` 只建表，无写入点（Step 7/9/11/12）；
- `page.description`/`cover_url`/`tags`/`allowed_datasources`/`last_gate_report` 与 `page_version.source_code`/`security_scan`/`scan_result` 均无写入点（Step 9/10/15）；
- `gen_session.attachments` 目前恒为 `[]`：`create_or_get()` 未透传 attachments，附件仍只从 `job.request_payload` 读；
- 旧库 `sinan` 的历史 Session/PageVersion 在新库中不可见，未做数据迁移（学习项目有意跳过）；
- 无迁移工具，后续模型变更仍需重建库，有真实数据后必须补 Alembic；
- `next_version()` 与 `save()` 非原子，同 marker 并发生成会撞 `uk_marker_version`（Step 6 之前既有行为）；
- 上述结构对齐尚未做黑盒验证，需在 Step 15 与参考项目做同输入下的表数据对照。
