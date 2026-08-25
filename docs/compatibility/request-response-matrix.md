# 请求与响应兼容性矩阵

## 生成与流式请求

| 场景 | 参考项目 | 当前 sinan | 差异/验证 |
|---|---|---|---|
| 新建生成 | `POST /api/page/generate`，认证，SSE 200 | `POST /api/v1/generate`，无认证，JSON `{session_id,status}` | 路径、认证、协议均不同；需 TestClient/真实 SSE 验证 |
| 请求字段 | `prompt(min=2)`、`session_id`、`marker`、附件、模板、数据源、知识库、Skill、mode | 同字段集（Step 1 已对齐；`skill_keys`/`knowledge_sources`/`datasources` 自 Step 12 起真正生效） | 字段集已齐；`mode` 仍未使用（Step 13/14） |
| 空 prompt | Pydantic 422（空值/长度不满足） | 目前可进入创建流程 | 需锁定 HTTP 码和错误 JSON |
| 过长 prompt | 需以参考配置/模型实际限制验证 | 未声明上限 | 记录实际边界，不凭注释猜测 |
| 生成失败 | SSE 已建立后发送 `error` 事件，通常 HTTP 仍为 200 | SSE 中发送 `error`，Session 置 `failed` | 事件 payload、终止事件和重连行为不同 |
| 页面预览 | `/api/page/preview/{marker}` HTML | `/api/v1/page/{marker}` HTML | 路径不同；当前版本和预览 URL 由 `generation_runner.py:139` 写入 |
| 资源不存在 | 参考预览通常 404；Session 部分接口 HTTP 200、JSON 内容码 404 | 以当前路由实现为准 | 必须用矩阵测试锁定接口级行为 |

## 统一记录格式

每个黑盒用例应记录：请求方法和 URL、认证 Cookie、请求体、HTTP 状态码、响应头、完整响应体/SSE 原文、数据库快照、事件顺序、重连位置和结论。

## 错误协议待验证项

参考项目的 `AuthenticationError` 默认码为 401（`page/core/exceptions.py:14`），但未认证访问、资源越权、Pydantic 422、业务 400 必须分别测试，不能只按异常类推断。

## Step 2 差异状态

> 说明：以下基于当前工作区核对。配置/日志/请求上下文/异常协议已落地，认证跳转和多环境配置待后续 Step。

| 差异项 | Step 0 状态 | 当前状态 | 待验证 |
|---|---|---|---|
| trace_id / 访问日志 | 无 | 已实现（`app.py` 中间件 + `context.py` + `sinan-access.log`） | 需发一次请求确认日志含 trace_id 且响应可关联 |
| 统一错误响应体 | 随机 500 | 已实现（全局 `SinanError` 处理器返回 `{"error": message}`，status=code，与参考一致） | 需触发一次 `SinanError` 确认响应体/状态码 |
| 错误类型区分 | 不可区分 | 已实现（401/403/404/409/500 子类，`core/exceptions.py`） | 认证/越权/404/业务错误需分别黑盒验证 |
| AuthenticationError 认证失败响应 | 未实现 | 暂不实现（已评估跳过）：认证属通用工程能力，非 agent 核心，个人使用暂用固定用户 `anonymous` | 无需验证；将来需要登录时再做 Step 3 |
| RUN_ENV 多环境配置 | 单一 settings | 仍为单一 settings（无 dev/sandbox/online.config） | 待验证是否需纳入对齐范围 |

## Step 3 差异状态

> 结论：**暂不实现（已评估跳过）**。Step 3（认证/资源鉴权）依赖百度 UUAP/UGate，且属于 Web 通用工程能力，对学习 agent 核心机制无帮助，故评估后跳过。
> 保留过渡方案：沿用固定用户常量 `anonymous`（`generate.py`），使后续 Step 4+ 需要 `user_id` 的逻辑仍可运行。将来若需登录，再回头实现本 Step。

| 差异项 | Step 0 状态 | 当前状态 | 说明 |
|---|---|---|---|
| 身份来源 | user 来自请求（`anonymous` 常量） | 暂不实现（已评估跳过） | 沿用固定用户 `anonymous`，供 Step 4+ 使用 |
| 未认证访问受保护接口 | 无认证 | 暂不实现（已评估跳过） | 个人使用，暂不加 `login_required` |
| body 伪造 user_id | 无该字段 | 暂不实现（已评估跳过） | `GenerateRequest` 无 `user_id`，无冒充面 |
| 跨用户读/改 Session、Page | 无隔离 | 暂不实现（已评估跳过） | 单用户使用，暂无隔离需求 |
| UGate Token | 未实现 | 暂不实现（已评估跳过） | 无接外部平台需求；后台 Job 需 token 时再补 |
| 认证失败格式 | 未实现 | 暂不实现（已评估跳过） | 全局 `SinanError` 处理器仍可返回 401/403，但无接入点 |

## Step 12 差异状态

`GenerateRequest` 字段集在 Step 1 就已对齐，本 Step 只是让三个字段真正生效——生成入口未改动，
`generate.py` 的 `req.model_dump(mode="json")` 整体入 `payload`，新字段自然流到 `_build_state`。

| 差异项 | Step 0 状态 | 当前状态 | 待验证 |
|---|---|---|---|
| `skill_keys` | 接收但不使用 | 生效：显式强制选择并绕过路由（`runtime/tool_registry.resolve_explicit`） | 同 prompt + 同 skill_keys 下对照两边 `skill_result` payload |
| `knowledge_sources` | 接收但不使用 | 生效：本地文件解析后注入 `external_knowledge` | HTTP 源在 sinan 默认被拒（`success=false` + 明确 error），参考会真抓 |
| `datasources` | 接收但不使用 | 生效：解析成 `DataSourceConfig` 取数，结果经 `datasource_context` 注入 coder | `db:` 前缀返回 unsupported；`api:` 走 httpx 无凭证 |
| Skill 安装请求体 | 无该接口 | `{"skill_key": "<本地目录名>"}` | 与参考 `{"url": "<zip>"}` 不兼容，已在 api-matrix 登记豁免 |
| `SessionConfirmRequest` | `{confirmed, feedback}` | 增加 `link` / `knowledge_sources` / `skill_keys` | 参考 `/confirm` 是无模型自由 dict，本就按 Step 8 说明豁免 |
| `SessionIterateRequest` | `{feedback, mode, attachments}` | 增加 `knowledge_sources` / `skill_keys` | 同上 |
| `DataSourceConfig` | `type/endpoint/schema_url/sample_data` | 扩展为 11 字段（含 `data_schema`/`timeout`/`error_policy`/`params`/`path`/`query`/`ref`/`name`） | 参考无对应模型，属 sinan 显式化增量，不参与逐字段对照 |
