# 持久化与存储兼容性矩阵

> 库隔离说明（Step 6 起）：本分支连接独立新库 `sinan_v2`，Redis 用 `db 1`
> （`sinan/config/settings.py:15,20`）。Step 5 及之前的分支继续使用 `sinan` / `db 0`。
> 库名写在 `settings.py` 而不是 `.env`，因为 `.env` 被 gitignore、为所有分支共用，
> 写进 `.env` 会导致切回旧分支时旧代码也连到新库。

| 对象 | 参考项目 | 当前 sinan | 差异 |
|---|---|---|---|
| Session | `GenerationSession`，含用户、状态、步骤、需求、marker、messages/attachments、逻辑删除 | `gen_session`（Step 6 重建，`tables.py:20`），新增 `pipeline_state`/`title`/`requirement_doc`/`messages`/`attachments`/`template_id`/`fix_rounds`/`verification_score`/`gate_reports`/`model_versions`/`is_deleted` 三列 | 字段已对齐；status 取值改为 active/paused/completed/failed/archived；sinan 额外保留 `prompt`/`iteration`/`total_tokens` |
| Job | `GenerationJob`，MySQL 持久化、租约和重连复用 | `generation_job`（Step 4，`tables.py:103`），status 默认值取自 `JobStatus`，取值含 `waiting` | 结构已对齐；`waiting` 自 Step 7 起有写入点（`mark_waiting`，analyst 挂起） |
| 步骤 | session 消息/审计及运行时记录 | `gen_session_step`（`tables.py:75`） | sinan 独有的细粒度审计表，参考侧用 messages + artifact 承载，语义不逐字对齐 |
| Page | 参考 `Page`（marker unique、current_version、published_version、published_to、quality_score） | `page`（Step 6 新增，`tables.py:165`），字段按参考 1:1 建立 | 已对齐；`allowed_datasources`/`cover_url`/`tags`/`description` 暂无写入点 |
| PageVersion | 参考版本快照，正文在 BOS（bos_path/entry_file/file_list/content_hash/security_scan/harness_score/repair_rounds） | `page_version`（Step 6 重建，`tables.py:200`），列位已对齐；正文仍走 `html_content`，`bos_path`/`file_list` 可空；已卸掉 `status`/`owner`/`updated_at` | 存储介质未对齐，待 Step 9 接对象存储后把 `bos_path` 收紧为非空 |
| Artifact | 参考 `GenerationArtifact`，支持类型和内容读取；写入在 `harness/orchestrator._save_checkpoint()` 里经 `session_store.save_artifact()` 落 BOS + 表 | `generation_artifact`（Step 6 新增，`tables.py:137`），`metadata` 列以属性名 `meta` 映射（`metadata` 是声明式保留名）；Step 9 起迁到 `services/artifact_store.py` | Step 9 已解决 ✅：`artifact_store.save_artifact()` 写 `analysis`/`design`/`verification` 三类；内容 < 64KB 入 `content` 列，>= 64KB 卸载到 LocalStorage，`bos_path` 写 `local://...` URI；`code` 类型通过 `save_code_snapshot()` 提供写入点（Step 10 接入）；参考写 BOS，sinan 用 LocalStorage（待生产接入时切换 `storage_type=bos`）|
| Harness checkpoint | 参考另有 `harness_checkpoint` 表 + Redis 双层 checkpoint（`page/harness/checkpoint.py`） | 无该表，checkpoint 仍由 LangGraph `MemorySaver` 承担 | 未对齐（已知差异）：进程重启后图内 checkpoint 丢失，恢复依赖 Job 重跑；Step 9 完成 artifact_store 后该差异收窄，但 harness_checkpoint 表本身不计划实现 |
| 上传附件 | 参考上传服务 + `generation_session.attachments` JSON，无独立表 | `attachment`（Step 6 新增，`tables.py:234`）；Step 9 起有写入点 | Step 9 已解决 ✅：`/api/page/upload` 调用 `data_service.parse_and_store()` → LocalStorage → `session_store.save_attachment()` 写 attachment 表；`session.attachments` 改为 file_id 字符串列表；`_hydrate_attachments` 优先查 attachment 表，旧路径（`attachment_storage_path`）降为兜底；`attachment.user_id` 仍为空，待 Step 3 认证补充 |
| Skill / Template | `skill_definition` / `page_template` | 同名表已建（Step 6，`tables.py:256,277`），无读写点 | 结构对齐，行为待 Step 11/12 |
| sys_user / buddy_profile | 参考存在 | 不建表 | 有意不对齐：认证 Step 3 已定"暂不实现"；buddy 与页面生成无关 |
| 事件 | Redis List，带 seq | Redis List + INCR seq（Step 5）：`sinan:generation:events:{sid}`，上限 1000 条，终止事件后 TTL 120s；本分支 `redis_db=1` | 持久化与回放已对齐 |
| 迁移 | 由 DBA/外部管理 | 无迁移体系：开发期靠 `init_db()` 的 `create_all()`；Step 6 的模型升级采用「新建空库 + create_all」，旧库 `sinan` 原样保留 | 未对齐：Alembic 推迟到有真实数据需保留时再引入 |
| Runtime checkpoint | LangGraph/runtime checkpoint | 由 graph 配置 thread_id，未形成对外恢复协议 | 待验证 |

## 写入路径

- 页面：`sinan/services/page_store.py:save()` 在单个事务里 upsert `page` + 插入 `page_version` + 推进 `current_version`，并写 `content_hash`/`code_size`/`file_list`/`harness_score`/`repair_rounds`；发布走 `publish()`（完整链路 Step 10）。Step 7 起 `harness_score` 是真实质量分（`compute_quality_score`），`repair_rounds` 取 `fix_round`。
- 会话：`session_store.create()` 落 `status=active` + `pipeline_state=init` + `title`；Step 7 起 `harness/orchestrator._persist()` 在每节点后写 `current_step` / `pipeline_state` / `gate_reports`（JSON 文本）；完成时 runner 回写 `marker`/`version`/`preview_url`/`pipeline_state=delivered`/`fix_rounds`/`verification_score`；挂起时写 `status=paused` + `pipeline_state=user_confirm` + `requirement_doc`（`generation_runner.py`）。
- 产物：Step 9 起由 `services/artifact_store.ArtifactStore.save_artifact()` 统一写入，`harness/orchestrator._persist()` 调用它；内容 < 64KB 写 `content` 列，>= 64KB 通过 `LocalStorage` 卸载到 `./output/storage/artifacts/`，`bos_path` 记 `local://...` URI。落库失败只记日志，不打断流水线。
- 附件：Step 9 起由 `/api/page/upload` → `data_service.parse_and_store()` → `session_store.save_attachment()` 写 `attachment` 表；原始文件和解析 JSON 均落 LocalStorage（`./output/storage/attachments/`）；`session.attachments` 由完整元数据对象改为 file_id 字符串列表；runner `_hydrate_attachments` 优先查表，旧 `/tmp/sinan_attachments/` 路径降为兜底。
- 读取：`page_version` 只提供快照字段，页面级状态（status/current_version/published_version）统一从 `page` 主表读（`api/routes/pages.py`、`api/routes/preview.py`）。

## 遗留项

- `page_version.bos_path` 仍为空，正文仍在 `html_content`；Step 9 已建好 StorageBackend 基础，Step 10 完成 page_service 后统一写入；
- `skill_definition`、`page_template` 只建表，无写入点（Step 11/12）；
- `harness/validators/browser_validator.py` 自 Step 7 起无引用点，渲染校验已收敛到 `harness/validators/render.py`；文件保留待 Step 13 复用或删除；
- `gen_session_step.contract_result` / `gate_decision` 两列仍无写入点：契约违规现存于 state 的 `contract_errors`（不落库），门禁决策落 `gen_session.gate_reports`；
- `page.description`/`cover_url`/`tags`/`allowed_datasources`/`last_gate_report` 与 `page_version.source_code`/`security_scan`/`scan_result` 均无写入点（Step 10/15）；
- `/api/storage/{key}` 路由尚未注册（`LocalStorage.signed_url` 返回此路径），Step 10 完善 preview 路由时一并添加；
- `attachment.user_id` 列在 upload 路由写入时恒为空，依赖 Step 3 认证完善后补充；
- `gen_session.attachments` 的历史数据格式为完整元数据对象，Step 9 后新写入改为 file_id 列表；两种格式已在 `save_attachment` 和 `_hydrate_attachments` 中兼容处理；
- 旧库 `sinan` 的历史 Session/PageVersion 在新库中不可见，未做数据迁移（学习项目有意跳过）；
- 无迁移工具，后续模型变更仍需重建库，有真实数据后必须补 Alembic；
- `next_version()` 与 `save()` 非原子，同 marker 并发生成会撞 `uk_marker_version`（Step 6 之前既有行为）；`artifact_store.save_artifact()` 的 `max(version)+1` 同理非原子，同 session 同类型并发会撞 `uk_artifact_session_type_version`（当前流水线内串行，暂不加锁）；
- 上述结构对齐尚未做黑盒验证，需在 Step 15 与参考项目做同输入下的表数据对照。
