# API 兼容性矩阵

本矩阵是 Step 0 的行为基线。参考实现位于
`/Users/zhanghj/Documents/baidu/project/baidu/gcloud/page/page`；状态码和认证结论以源码为准，尚未替代真实服务的黑盒验证。

## 参考项目公开 API

| 方法 | 路径 | 认证 | 成功 | 参考位置 |
|---|---|---|---|---|
| GET | `/api/page/health` | 否 | 200 JSON | `page/api/routes/health.py:5` |
| GET | `/api/page/ready` | 否 | 200 JSON | `page/api/routes/health.py:14` |
| GET | `/api/v1/callbackUrl` | UUAP 回调 | 302 | `page/api/routes/auth.py:18` |
| GET | `/api/v1/loginUser` | 是 | 200 JSON | `page/api/routes/auth.py:32` |
| POST | `/api/page/generate` | 是 | 200 SSE | `page/api/routes/generate.py:47` |
| GET | `/api/page/ugate-token/cache/refresh` | 是 | 200 JSON | `page/api/routes/generate.py:81` |
| POST | `/api/page/upload` | 是 | 200 JSON | `page/api/routes/upload.py:134` |
| POST | `/api/page/host` | 当前无显式依赖 | 200 JSON | `page/api/routes/hosting.py:28` |
| GET/POST/PUT/DELETE | `/api/page/proxy/{marker}/{path:path}` | 当前无显式依赖 | 上游状态 | `page/api/routes/proxy.py:14` |
| GET | `/api/page/preview/{marker}` | 否 | 200 HTML | `page/api/routes/preview.py:41` |
| GET | `/api/page/preview/{marker}/v{version}` | 否 | 200 HTML | `page/api/routes/preview.py:54` |
| GET | `/api/page/preview/{marker}/live/{session_id}` | 否 | 200 HTML | `page/api/routes/preview.py:64` |
| GET | `/api/page/pages/{marker}/versions` | 是 | 200 JSON | `page/api/routes/pages.py:18` |
| GET | `/api/page/pages/{marker}/data` | 是 | 200 JSON | `page/api/routes/pages.py:41` |
| GET | `/api/page/pages/{marker}/download/{file_id}` | 是 | 200 文件流 | `page/api/routes/pages.py:48` |
| GET | `/api/page/pages/{marker}/messages` | 是 | 200 JSON | `page/api/routes/pages.py:67` |
| GET | `/api/page/pages/{marker}/artifacts` | 是 | 200 JSON | `page/api/routes/pages.py:74` |
| GET | `/api/page/pages/{marker}/artifacts/{artifact_type:path}` | 是 | 200 内容 | `page/api/routes/pages.py:81` |
| GET | `/api/page/session/{session_id}` | 是 | 200 JSON | `page/api/routes/session.py:331` |
| GET | `/api/page/session/{session_id}/messages` | 是 | 200 JSON | `page/api/routes/session.py:265` |
| GET | `/api/page/session/{session_id}/code` | 是 | 200 JSON | `page/api/routes/session.py:282` |
| POST | `/api/page/session/{session_id}/code` | 是 | 200 JSON | `page/api/routes/session.py:301` |
| POST | `/api/page/session/{session_id}/resume` | 是 | 200 SSE | `page/api/routes/session.py:350` |
| POST | `/api/page/session/{session_id}/confirm` | 是 | 200 SSE | `page/api/routes/session.py:417` |
| GET | `/api/page/session/{session_id}/harness` | 是 | 200 JSON | `page/api/routes/session.py:696` |
| POST | `/api/page/session/{session_id}/iterate` | 是 | 200 SSE | `page/api/routes/session.py:713` |
| GET | `/api/page/session/{session_id}/generation-job` | 是 | 200 JSON | `page/api/routes/session.py:1546` |
| GET | `/api/page/session/{session_id}/events` | 是 | 200 SSE | `page/api/routes/session.py:1582` |
| POST | `/api/page/session/{session_id}/abort` | 是 | 200 JSON | `page/api/routes/session.py:1599` |
| GET | `/api/page/session/{session_id}/data` | 是 | 200 JSON | `page/api/routes/session.py:1612` |
| GET | `/api/page/session/{session_id}/download/{file_id}` | 是 | 200 文件流 | `page/api/routes/session.py:1619` |
| GET | `/api/page/s` | 是 | 200 JSON | `page/api/routes/session.py:1637` |
| POST | `/api/page/templates` | 是 | 200 JSON | `page/api/routes/template.py:17` |
| PATCH | `/api/page/templates/{template_id}/offline` | 是 | 200 JSON | `page/api/routes/template.py:73` |
| GET | `/api/page/templates` | 是 | 200 JSON | `page/api/routes/template.py:89` |
| GET | `/api/page/prompt/templates` | 是 | 200 JSON | `page/api/routes/prompt_template.py:15` |
| GET | `/api/page/prompt/templates/{template_id}` | 是 | 200 JSON | `page/api/routes/prompt_template.py:41` |
| GET | `/api/page/admin/skills` | 是 | 200 JSON | `page/api/routes/admin_skills.py:152` |
| POST | `/api/page/admin/skills/install` | 是 | 200 JSON | `page/api/routes/admin_skills.py:167` |
| PATCH | `/api/page/admin/skills/{skill_key}/status` | 是 | 200 JSON | `page/api/routes/admin_skills.py:178` |
| PATCH | `/api/page/admin/skills/{skill_key}` | 是 | 200 JSON | `page/api/routes/admin_skills.py:191` |
| DELETE | `/api/page/admin/skills/{skill_key}` | 是 | 200 JSON | `page/api/routes/admin_skills.py:209` |
| GET | `/api/page/buddy` | 是 | 200 JSON | `page/api/routes/buddy.py:21` |
| POST | `/api/page/buddy/profile` | 是 | 200 JSON | `page/api/routes/buddy.py:28` |
| POST | `/api/page/buddy/pet` | 是 | 200 JSON | `page/api/routes/buddy.py:35` |
| GET | `/api/page/trace/{session_id}` | 否 | 200 JSON | `page/api/routes/trace.py:163` |

## 当前 sinan API

| 方法 | 路径 | 认证 | 当前行为 | 位置 | Step 1 后状态 |
|---|---|---|---|---|---|
| GET | `/health` | 否 | 200 JSON | `sinan/api/routes/health.py:5` | 保留 |
| POST | `/api/v1/generate` | 否 | 创建任务并返回 JSON | `sinan/api/routes/generate.py:35` | 保留为兼容旧路径 |
| GET | `/api/v1/generate/{session_id}/stream` | 否 | 内存 SSE | `sinan/api/routes/generate.py:46` | 保留为兼容旧路径 |
| POST | `/api/page/generate` | 否（Step 3 加认证） | 200 SSE，直接流式返回（已实现） | `sinan/api/routes/generate.py:68` | **Step 1 已实现** |
| GET | `/api/v1/page/{marker}` | 否 | 最新版本 HTML | `sinan/api/routes/preview.py:23` | 保留 |
| GET | `/api/v1/page/{marker}/versions` | 否 | 版本列表 | `sinan/api/routes/preview.py:48` | 保留 |
| GET | `/api/v1/page/{marker}/version/{version_num}` | 否 | 指定版本 HTML | `sinan/api/routes/preview.py:75` | 保留 |
| GET | `/api/page/preview/{marker}` | 否 | 最新版本 HTML | `sinan/api/routes/preview.py`（Step 1 待实施） | **Step 1 待实施** |
| GET | `/api/page/preview/{marker}/v{version}` | 否 | 指定版本 HTML | `sinan/api/routes/preview.py`（Step 1 待实施） | **Step 1 待实施** |
| GET | `/api/v1/generate/{session_id}/audit` | 否 | 步骤审计 | `sinan/api/routes/audit.py:11` | 保留 |
| POST | `/api/v1/data/upload` | 否 | 本地附件解析 | `sinan/api/routes/data.py:11` | 保留 |
| GET | `/api/page/session/{session_id}` | 否（Step 3 加认证） | 桩实现，待 Step 4 填充 | `sinan/api/routes/session.py`（Step 1 待实施） | **Step 1 待实施（桩）** |
| GET | `/api/page/pages/{marker}/versions` | 否（Step 3 加认证） | 桩实现，待 Step 10 填充 | `sinan/api/routes/pages.py`（Step 1 待实施） | **Step 10 已实现**（含 published_version/harness_score 等完整字段，格式 `{"code":0,"data":{...}}`） |
| POST | `/api/page/upload` | 否（Step 3 加认证） | 桩实现，待 Step 9 填充 | `sinan/api/routes/upload.py`（Step 1 待实施） | **Step 1 待实施（桩）** |

## Step 8 新增会话动作 API（方案就绪，待实施）

参考对应：`page/api/routes/session.py` 的 `/confirm`(:417)、`/resume`(:350)、`/iterate`(:713)、`/abort`(:1599)。
sinan 落地位置统一在 `sinan/api/routes/session.py`（已注册于 `app.py:87`，无需改 app）。

| 方法 | 路径 | 认证 | 计划行为 | sinan 落点 | 状态 |
|---|---|---|---|---|---|
| POST | `/api/page/session/{session_id}/confirm` | 过渡期无（Step 3 加） | 200 SSE：确认继续生成 / 拒绝保留 paused | `session.py` + `session_action_service.confirm` | 方案就绪 |
| POST | `/api/page/session/{session_id}/iterate` | 同上 | 200 SSE：多轮修改，产新 PageVersion | `session.py` + `session_action_service.iterate` | 方案就绪 |
| POST | `/api/page/session/{session_id}/abort` | 同上 | 200 JSON：取消并落 cancelled | `session.py` + `session_action_service.abort` | 方案就绪 |
| POST | `/api/page/session/{session_id}/resume` | 同上 | 200 SSE：从挂起点继续 | `session.py` + `session_action_service.resume` | 方案就绪（MemorySaver 非持久，等价于 confirm 续跑，见说明） |

> 差异说明：
> - 参考 `/confirm`、`/iterate` 请求体是无模型的自由 dict（含 `feedback`/`content`/`message`/`link`/`token`/`attachments` 等）；sinan 按实施计划 8.1 引入 `SessionConfirmRequest`/`SessionIterateRequest`/`SessionAbortRequest` 强类型模型，字段更收敛，Step 15 逐字段对照时按此豁免。
> - 参考 `/resume` 依赖 `runtime_session_store` 检查点；sinan 图用 `MemorySaver`（进程内、不跨重启），故 resume 实为"用 Session 内已存的 `requirement_doc` + 当前页面重跑图续跑"，不是真检查点回放——属两边机制差异，记为待黑盒验证。
> - 参考 `/abort` 返回 JSON（非 SSE），sinan 对齐为 JSON。

## 已确认差异（Step 0 基线）

- 路径前缀、资源 API、认证层和请求语义不一致。
- 参考生成请求校验 `prompt` 最短 2 个字符；当前请求模型未声明该约束。
- 参考生成建立 SSE；当前 POST 返回普通 JSON，SSE 需要另行 GET。
- 当前没有参考项目的 Session、Job、确认、取消、恢复、模板、Skill、Artifact 和发布 API。

## Step 1 差异状态

> 说明：以下状态基于当前工作区（分支 `phase-6`，未提交改动）核对。生成侧已落地，资源侧路由/预览兼容路由尚未落地。

| 差异项 | Step 0 状态 | 当前状态 | 待验证 |
|---|---|---|---|
| 生成 API 主路径 `/api/page/generate` | 缺失 | 已实现（`generate.py:68`，直接返回 SSE） | 需运行 `curl -N POST /api/page/generate` 确认流式响应 |
| `prompt` 最小长度校验（min=2） | 无约束 | 已实现（`contracts.py:65` `Field(..., min_length=2)`，与参考一致） | 需运行空/单字符 prompt 确认 422 |
| `session_id`/`marker`/`mode` 等字段 | 缺失 | 已实现（`contracts.py:64-78`，字段集与参考完全一致） | 字段接收，内部暂不使用 |
| 预览路径 `/api/page/preview/{marker}`、`/v{version}` | 缺失 | 已实现（`preview.py:page_router`） | - |
| 认证 | 无 | 无（Step 3 加） | 仍待解决 |
| Session/Job/确认/取消/恢复 API | 缺失 | **待实施**（session/pages/upload 桩文件尚未创建） | 待 Step 1 建桩、Step 4-10 实现 |
| `POST /api/page/generate` SSE 使用内存 Queue | — | 已替换为 Redis List 持久化事件流（Step 5），`Last-Event-ID`/`cursor` 断线续传，`ping=30` | 需 curl 断线重连确认不丢不重 |
| SSE 事件 ID 与回放 | 无 ID、无回放 | 已实现（`models/events.py`、`services/generation_event_bus.py`） | 待 Step 15 双项目 SSE 原文对照 |

## Step 10 新增 API

| 方法 | 路径 | 认证 | 行为 | 位置 | 状态 |
|---|---|---|---|---|---|
| POST | `/api/page/host` | 否（Step 3 加） | 上传 HTML/ZIP，安全扫描，写 page_version；返回 preview_url | `api/routes/hosting.py` | **Step 10 已实现** |
| POST | `/api/page/pages/{marker}/publish` | 否（Step 3 加） | 发布指定版本，写 published_version + status=published | `hosting.py` + `page_service.publish_page` | **Step 10 已实现** |
| POST | `/api/page/pages/{marker}/unpublish` | 否（Step 3 加） | 取消发布，status 回退 preview，清 published_version | `hosting.py` + `page_service.unpublish_page` | **Step 10 已实现** |
| POST | `/api/page/pages/{marker}/rollback` | 否（Step 3 加） | 回滚 current_version 指针，不删历史版本 | `hosting.py` + `page_service.rollback_version` | **Step 10 已实现** |
| GET | `/api/page/preview/{marker}/live/{session_id}` | 否 | 生成中实时预览，每 3s 自动刷新 | `preview.py:preview_live` | **Step 10 已实现** |
| GET | `/api/storage/{key:path}` | 否 | 服务 LocalStorage 静态文件（`signed_url` 遗留项） | `preview.py:storage_router` | **Step 10 已实现** |
| GET | `/api/page/pages/{marker}/data` | 否（Step 3 加） | marker 关联附件列表 | `pages.py:get_page_data` | **Step 10 已实现** |
| GET | `/api/page/pages/{marker}/download/{file_id}` | 否（Step 3 加） | 下载附件文件 | `pages.py:download_page_attachment` | **Step 10 已实现** |
| GET | `/api/page/pages/{marker}/messages` | 否（Step 3 加） | marker 关联会话消息列表 | `pages.py:get_page_messages` | **Step 10 已实现** |
| GET | `/api/page/pages/{marker}/artifacts` | 否（Step 3 加） | 流水线产物列表 | `pages.py:get_page_artifacts` | **Step 10 已实现** |
| GET | `/api/page/pages/{marker}/artifacts/{artifact_type:path}` | 否（Step 3 加） | 下载特定产物 JSON | `pages.py:download_page_artifact` | **Step 10 已实现** |

## Step 12 新增 API

参考对应：`page/api/routes/admin_skills.py` 的 5 个端点（`:152,167,178,191,209`）。

| 方法 | 路径 | 认证 | 行为 | 位置 | 状态 |
|---|---|---|---|---|---|
| GET | `/api/page/admin/skills` | 否（Step 3 已评估跳过） | 列出已入库 Skill（不含 content），支持 `status`/`visibility` 过滤 | `api/routes/admin_skills.py:list_skills` | **Step 12 已实现** |
| GET | `/api/page/admin/skills/local` | 否 | **sinan 增量**：列出本地 `sinan/skills/` 下的包及是否已入库，附 `skills_dir` 绝对路径 | `admin_skills.py:list_local_skills` | **Step 12 已实现** |
| POST | `/api/page/admin/skills/install` | 否 | 从本地目录安装（请求体 `{"skill_key": "..."}`）；包不存在 404，key 含路径分隔符 400 | `admin_skills.py:install_skill` | **Step 12 已实现** |
| PATCH | `/api/page/admin/skills/{skill_key}/status` | 否 | 启用 / 停用；非 `enabled|disabled` 由 Pydantic 拦为 422 | `admin_skills.py:update_skill_status` | **Step 12 已实现** |
| PATCH | `/api/page/admin/skills/{skill_key}` | 否 | 改 `output_type`/`name`/`description` | `admin_skills.py:update_skill` | **Step 12 已实现** |
| DELETE | `/api/page/admin/skills/{skill_key}` | 否 | 删表记录（不删本地包目录） | `admin_skills.py:delete_skill` | **Step 12 已实现** |

已用 httpx ASGITransport 实测：`/local` 200、list 200、install 200 / 404 / 400、status 200 / 422、PATCH 404、DELETE 404。

> 已确认差异（Step 15 按此豁免）：
> - `POST /install` 请求体不同——参考是 `{"url": "<BOS zip URL>"}` 并会下载解压 + chmod，
>   sinan 是 `{"skill_key": "<本地目录名>"}`，只扫描解析不出网。原因：学习项目不接 BOS/内网平台。
> - sinan 多一个 `GET /local`；参考无此端点（参考的包来源是远端，没有"本地未入库"这个概念）。
> - 参考 `PATCH /{skill_key}` 对不存在的 key 会**创建**一条新记录（`create_or_update_skill` 的副作用）；
>   sinan 先查存在性，不存在返回 404。这是有意收紧。
> - 参考五个端点都挂 `login_required`；sinan 无认证（Step 3 已评估跳过）。

