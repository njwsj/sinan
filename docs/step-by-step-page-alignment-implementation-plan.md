# sinan 与原项目 page 百分百对齐：逐 Step 实施方案

本文面向项目 `/Users/zhanghj/Documents/learn/sinan`，以原项目
`/Users/zhanghj/Documents/baidu/project/baidu/gcloud/page` 为行为基准。

目标不是让两个项目的文件名完全相同，而是让两边在相同输入下具备一致的：

- API 路径、请求字段、响应字段和 HTTP 状态码；
- 认证和资源权限行为；
- Session、Job、Pipeline 的状态变化；
- SSE 事件名称、字段、顺序、ID 和断线回放；
- 生成分支和运行时选择；
- 页面、版本、附件和 Artifact 的持久化结果；
- 用户确认、取消、恢复和多轮修改行为；
- 预览、发布、托管和安全检查行为；
- 异常、日志和可观测性行为。

“百分百对齐”的最终判断标准是黑盒兼容测试，而不是目录结构相似。

---

## 0. 当前基线与总体顺序

### 0.1 当前 `sinan` 已经具备的能力

当前项目已有：

```text
Prompt
  → Analyzer
  → Designer
  → Coder
  → Verifier
  → Fixer
  → PageVersion
  → Redis 持久化 SSE（Step 5 起，可回放）
```

主要文件：

```text
sinan/agents/graph.py
sinan/agents/state.py
sinan/agents/analyzer.py
sinan/agents/designer.py
sinan/agents/coder.py
sinan/agents/verifier.py
sinan/agents/fixer.py
sinan/harness/gates.py
sinan/harness/state_machine.py
sinan/models/tables.py
sinan/services/generation_runner.py
sinan/services/generation_event_bus.py
sinan/api/routes/generate.py
```

### 0.2 原项目的完整能力

原项目的完整链路是：

```text
认证
  → 请求上下文
  → Session / Job
  → 附件和数据摄取
  → Intent / Router
  → Analysis
  → 用户确认
  → Design
  → Code Generation
  → Harness Contract / Gate
  → 自动验证和修复
  → 用户多轮修改
  → Artifact / Page / PageVersion
  → SSE 事件回放
  → Preview
  → Hosting / Publish
```

同时支持：

```text
Native LangGraph
Claude Code Runtime
Opencode Runtime
Skill
知识库
页面模板
Prompt Template
```

### 0.3 必须遵守的施工顺序

不要直接从 Skill 或 Opencode 开始。推荐顺序：

```text
Step 0   建立黑盒基线
Step 1   对齐 API 和错误协议
Step 2   对齐配置、日志、请求上下文
Step 3   对齐认证和资源权限
Step 4   拆分 Session / Job，建立可恢复任务
Step 5   重建 SSE 事件协议和 Redis 回放
Step 6   重建数据模型和数据库迁移
Step 7   对齐 Native LangGraph 和 Harness
Step 8   对齐用户确认、取消、恢复和多轮修改
Step 9   对齐附件、Artifact、Storage 和 BOS
Step 10  对齐页面、版本、预览和发布
Step 11  对齐 Template、Prompt Template、Skill
Step 12  对齐知识库和数据源
Step 13  对齐 Claude Code Runtime
Step 14  对齐 Opencode 和 Hybrid Runtime
Step 15  完成安全、可观测性和兼容性验收
```

前面的 Step 没完成时，后面的 Step 不要急着实现。

---

# Step 0：建立行为基线和兼容性矩阵

## 目标

先明确“原项目的实际行为是什么”，避免只根据类名或注释猜测。

这一阶段主要写文档和测试，不改核心业务逻辑。

## 新增文件

在当前项目新增：

```text
docs/compatibility/api-matrix.md
docs/compatibility/request-response-matrix.md
docs/compatibility/state-matrix.md
docs/compatibility/event-matrix.md
docs/compatibility/storage-matrix.md
docs/compatibility/runtime-matrix.md
docs/compatibility/behavior-cases.md
```

新增测试目录：

```text
tests/compatibility/
tests/unit/
tests/integration/
tests/e2e/
```

## 怎么做

每个行为使用统一格式：

```text
场景：
输入：
原项目响应：
原项目数据库变化：
原项目事件序列：
sinan 当前响应：
sinan 当前数据库变化：
sinan 当前事件序列：
差异：
目标行为：
验证方式：
```

至少记录以下场景：

1. 新建页面；
2. Prompt 为空；
3. Prompt 过长；
4. 普通聊天输入；
5. 页面生成失败；
6. 页面生成中客户端断线；
7. 生成完成后重新连接；
8. 取消生成；
9. 服务重启后恢复任务；
10. 复用已有 Session；
11. 修改已有页面；
12. 用户确认；
13. 用户拒绝；
14. 用户反馈后二次生成；
15. 上传 Excel；
16. 上传 CSV；
17. 上传图片；
18. 上传非法 ZIP；
19. 使用页面模板；
20. 使用 Prompt Template；
21. 使用 Skill；
22. 使用知识库链接；
23. 页面预览；
24. 页面版本预览；
25. 页面发布；
26. 未认证访问；
27. 访问其他用户的 Session；
28. 访问其他用户的 Page。

## 原项目参考位置

```text
page/api/app.py
page/api/routes/generate.py
page/api/routes/session.py
page/api/routes/pages.py
page/api/routes/preview.py
page/api/routes/upload.py
page/api/routes/hosting.py
page/models/contracts.py
page/models/enums.py
page/models/tables.py
page/services/generation_runner.py
page/services/generation_event_bus.py
```

## 验收标准

Step 0 完成后必须能回答：

- 原项目所有公开 API 是什么；
- 每个 API 是否需要认证；
- 每个生成场景的事件顺序是什么；
- 每种任务状态如何转移；
- 页面版本在哪里保存；
- 失败、取消、等待确认如何表现；
- 哪些行为当前 `sinan` 不一致。

---

# Step 1：对齐 API 路径、请求和响应

## 目标

先让 `sinan` 的外部 HTTP 表面和原项目一致。内部可以暂时继续调用当前 LangGraph，但不能继续使用不同的 API 语义。

## 1.1 修改 `sinan/api/app.py`

当前文件：

```text
sinan/api/app.py
```

当前主要职责：

- 创建 FastAPI；
- 初始化数据库；
- 注册少量 `/api/v1` 路由；
- 启动和关闭生命周期。

当前注册方式类似：

```python
app.include_router(generate_router, prefix="/api/v1")
app.include_router(preview_router, prefix="/api/v1")
```

### 修改方式

将统一业务前缀改为原项目使用的：

```text
/api/page
```

短期可以兼容保留旧路径，但新路径必须作为主路径。

建议路由注册结构：

```python
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(generate.router)
app.include_router(session.router)
app.include_router(pages.router)
app.include_router(preview.router)
app.include_router(upload.router)
app.include_router(hosting.router)
app.include_router(template.router)
app.include_router(prompt_template.router)
app.include_router(admin_skills.router)
app.include_router(trace.router)
```

### 原项目参考

```text
page/api/app.py:133-146
```

## 1.2 修改 `sinan/api/routes/generate.py`

当前文件：

```text
sinan/api/routes/generate.py
```

当前行为：

```text
POST /api/v1/generate
  → 创建 GenSession
  → asyncio.create_task()
  → 返回 JSON

GET /api/v1/generate/{session_id}/stream
  → 订阅 asyncio.Queue
```

原项目行为：

```text
POST /api/page/generate
  → 创建或复用 Session
  → 创建或复用 Job
  → 确保 Job 运行
  → replay 历史事件
  → 订阅后续事件
  → 直接返回 EventSourceResponse
```

原项目参考：

```text
page/api/routes/generate.py:47-78
page/api/routes/generate.py:108-125
```

### 修改步骤

第一步，先扩展请求模型：

```python
class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=2)
    session_id: str | None = None
    marker: str | None = None
    attachments: list[dict] = Field(default_factory=list)
    preset: str | None = None
    template_id: str | None = None
    prompt_template_id: str | None = None
    datasources: list[str] = Field(default_factory=list)
    knowledge_sources: list[str] = Field(default_factory=list)
    skill_keys: list[str] = Field(default_factory=list)
    mode: str | None = None
```

第二步，暂时保留旧的 JSON 接口作为兼容入口：

```text
POST /api/v1/generate
```

第三步，新建原项目兼容入口：

```text
POST /api/page/generate
```

第四步，让新入口返回 SSE：

```python
return EventSourceResponse(
    subscribe_generation_events(session_id),
    ping=30,
)
```

第五步，把创建任务逻辑移出路由，放入：

```text
sinan/services/session_store.py
sinan/services/generation_job_store.py
```

这样路由只负责：

```text
解析请求
→ 调用应用服务
→ 返回 SSE
```

## 1.3 新增 Session、Page、Upload、Hosting 路由文件

新增：

```text
sinan/api/routes/session.py
sinan/api/routes/pages.py
sinan/api/routes/upload.py
sinan/api/routes/hosting.py
sinan/api/routes/template.py
sinan/api/routes/prompt_template.py
```

当前 `sinan` 的：

```text
sinan/api/routes/data.py
sinan/api/routes/preview.py
```

可以先保留内部实现，再由兼容路由适配到原项目路径和响应格式。

## 验收标准

```text
POST /api/page/generate
```

必须：

- 使用原项目路径；
- 接收原项目请求字段；
- 直接返回 SSE；
- 返回事件格式与原项目一致；
- 不再把 `user_id` 作为可信身份来源；
- 无效参数返回一致的错误结构。

---

# Step 2：对齐配置、日志、异常和请求上下文

## 目标

让服务启动、请求日志、trace_id 和异常返回行为一致。

## 2.1 修改 `sinan/config/settings.py`

当前文件：

```text
sinan/config/settings.py
```

需要补充配置分组：

```text
AppConfig
DatabaseConfig
RedisConfig
BOSConfig
AuthConfig
RuntimeConfig
StorageConfig
FeatureConfig
```

至少增加：

```text
app_name
debug
host
port
database_url
redis_url
bos_endpoint
bos_bucket
auth_mode
opencode_enabled
opencode_base_url
opencode_mode
max_generation_attempts
job_lease_seconds
event_retention_seconds
```

不要把所有配置继续放在一个无区分的 Settings 类里，否则后面很难判断配置属于哪个运行时。

## 2.2 修改 `sinan/core/logging.py`

当前只配置控制台日志。需要增加：

- `page.log`；
- `page-access.log`；
- rotating handler；
- trace_id；
- user_id；
- session_id；
- job_id；
- marker；
- 结构化访问日志。

原项目参考：

```text
page/api/app.py:21-65
page/api/context.py
```

## 2.3 新增 `sinan/api/context.py`

新增：

```text
sinan/api/context.py
```

实现 ContextVar：

```python
trace_id_var
request_user_var
session_id_var
job_id_var
```

并提供：

```python
new_trace_id()
get_trace_id()
get_request_user()
```

## 2.4 修改 `sinan/api/app.py`

增加 middleware：

```text
每次请求进入
  → 创建 trace_id
  → 解析用户上下文
  → 记录开始时间
  → 执行请求
  → 记录路径、状态码、耗时、用户、trace_id
```

## 2.5 修改 `sinan/core/exceptions.py`

当前只有简单的 `SinanError`。扩展为：

```python
class SinanError(Exception):
    message: str
    code: int
    error_code: str
    details: dict

class AuthenticationError(SinanError):
    ...

class AuthorizationError(SinanError):
    ...

class NotFoundError(SinanError):
    ...

class GenerationError(SinanError):
    ...

class JobConflictError(SinanError):
    ...
```

## 验收标准

- 同一个请求日志包含 trace_id；
- 错误响应不是随机 500；
- SSE 错误和普通 HTTP 错误都有稳定 error_code；
- 认证错误、权限错误、资源不存在错误可区分；
- 日志不泄露 token、原始密钥和完整敏感附件内容。

---

# Step 3：对齐认证和资源权限

## 目标

让用户身份来自认证上下文，而不是请求体中的 `user_id`。

## 3.1 新增 `sinan/services/web_auth.py`

新增：

```text
sinan/services/web_auth.py
```

实现：

```python
class AuthResult:
    username: str
    display_name: str | None
    authenticated: bool
    source: str
    token: str | None

async def login_required(request: Request) -> AuthResult:
    ...
```

开发阶段支持：

```text
AUTH_MODE=mock
```

生产阶段再接原项目的 UUAP/Web Auth。

## 3.2 修改 `sinan/api/routes/generate.py`

将：

```python
user_id = req.user_id
```

改为：

```python
auth: AuthResult = Depends(login_required)
user_id = auth.username
```

请求体可以暂时保留 `user_id` 字段用于兼容，但必须：

- 不把它作为可信身份；
- 如果和认证用户不同，忽略或返回错误；
- 在日志中记录实际认证用户。

## 3.3 新增资源权限服务

新增：

```text
sinan/services/authorization.py
```

提供：

```python
can_read_session(user_id, session_id)
can_write_session(user_id, session_id)
can_read_page(user_id, marker)
can_write_page(user_id, marker)
can_read_artifact(user_id, artifact_id)
```

Session、Page、Artifact、Attachment 的查询和修改都必须经过这个服务。

## 3.4 对齐 UGate Token

新增：

```text
sinan/services/ugate_token_store.py
```

先实现：

- 从请求 header 读取 token；
- token 标准化；
- 脱离请求的后台 Job 可以读取 token；
- token 不写入普通日志；
- token 缓存可以过期。

原项目参考：

```text
page/services/ugate_token_store.py
page/api/routes/generate.py:51-65
```

## 验收标准

必须通过：

1. 未认证访问受保护接口失败；
2. body 中伪造 `user_id` 不能冒充其他用户；
3. 用户 A 不能查看用户 B 的 Session；
4. 用户 A 不能修改用户 B 的 Page；
5. 后台 Skill Job 能使用正确用户的 token；
6. 鉴权失败格式与原项目一致。

---

# Step 4：拆分 Session 和 Job，建立可恢复任务

## 目标

替换当前：

```python
asyncio.create_task(...)
```

让任务拥有数据库生命周期、租约、重试和恢复能力。

## 4.1 修改 `sinan/models/tables.py`

保留当前 `GenSession`，但新增：

```python
class GenerationJob(Base):
    __tablename__ = "generation_job"

    job_id
    session_id
    marker
    user_id
    status
    request_payload
    lease_owner
    lease_until
    heartbeat_at
    attempts
    max_attempts
    error_message
    started_at
    finished_at
    created_at
    updated_at
```

字段设计参考：

```text
page/models/tables.py:68-88
```

## 4.2 新增 `sinan/services/generation_job_store.py`

新增：

```text
sinan/services/generation_job_store.py
```

实现：

```python
create_or_get_job(...)
get_job(job_id)
get_job_by_session(session_id)
claim_next_job(worker_id)
heartbeat(job_id, worker_id)
mark_running(job_id, worker_id)
mark_completed(job_id)
mark_failed(job_id, error)
mark_cancelled(job_id)
request_cancel(job_id)
release_lease(job_id, worker_id)
recover_expired_jobs()
```

核心要求：

- 同一个请求重复提交时可复用 Job；
- 只有拿到 lease 的 worker 才能执行；
- lease 过期后任务可以被恢复；
- 已完成 Job 不重复执行；
- 达到最大重试次数后进入 failed；
- cancel 后不能继续写入 completed。

## 4.3 修改 `sinan/services/generation_runner.py`

当前文件直接根据 session_id 执行生成。改成：

```text
run_job(job_id)
  → 查询 Job
  → 校验 lease
  → 加载 request_payload
  → 更新 Session running
  → 执行 Runtime
  → 定期 heartbeat
  → 保存 Artifact / PageVersion
  → 更新 Job 和 Session
```

建议拆出：

```python
async def run_job(job_id: str) -> None
async def execute_generation_pipeline(job: GenerationJob) -> None
async def heartbeat_loop(job_id: str, worker_id: str) -> None
async def finalize_job(job_id: str, result: GenerationResult) -> None
```

## 4.4 新增 `sinan/services/generation_supervisor.py`

新增：

```text
sinan/services/generation_supervisor.py
```

实现：

```python
start_supervisor()
stop_supervisor()
supervisor_loop()
```

循环逻辑：

```text
扫描 pending Job
  → 扫描 lease 过期 Job
  → claim
  → create_task(run_job)
  → 定时 heartbeat
```

## 4.5 修改 `sinan/api/app.py` 生命周期

启动：

```text
数据库
  → Redis
  → supervisor
```

关闭：

```text
停止接收新任务
  → 等待或标记当前 Job
  → 停止 supervisor
  → 关闭 Redis
  → 关闭数据库
```

## 验收标准

必须测试：

- 同一请求重复提交不会创建两个活跃 Job；
- Job 执行中进程重启后可恢复；
- worker 崩溃后 lease 最终过期；
- 任务最多执行 `max_attempts` 次；
- cancel 后不会产生 completed；
- 一个 Job 不会被两个 worker 同时执行。

---

# Step 5：重建 SSE 事件协议和 Redis 回放

## 目标

把当前进程内 `asyncio.Queue` 改造成与原项目一致的可持久化事件流。

## 5.1 新增 `sinan/models/events.py`

新增：

```text
sinan/models/events.py
```

定义：

```python
class GenerationEvent(BaseModel):
    event_id: str
    event: str
    session_id: str
    job_id: str | None
    marker: str | None
    timestamp: str
    data: dict
```

## 5.2 修改 `sinan/services/generation_event_bus.py`

当前实现：

```text
session_id → asyncio.Queue
```

位置：

```text
sinan/services/generation_event_bus.py
```

保留同样的抽象接口，但增加：

```python
publish(...)
replay(session_id, cursor)
subscribe(session_id, cursor)
get_last_event_id(session_id)
close(session_id)
trim(session_id)
```

内部实现（按参考项目实际做法，不是 Redis Stream）：

```text
Redis List
  → 事件 key：   sinan:generation:events:{session_id}
  → 序列号 key： sinan:generation:events:seq:{session_id}（INCR 生成）
  → event_id 为十进制整数字符串，可直接比较大小
  → 记录内容为 JSON：{"seq": N, "event": {GenerationEvent 全字段}}
  → LTRIM 保留最新 1000 条；终止事件后给 key 打 120s TTL
  → subscribe 用 1s 轮询 LRANGE，不用 pub/sub
```

> 参考项目 `page/services/generation_event_bus.py:12-17,146-185` 用的是 List + INCR，不是 Stream。
> 用 Stream 会让 `event_id` 变成 `1712-0` 形式的复合 ID，客户端无法按大小比较游标，与参考行为不兼容。

如果 Redis 不可用，开发环境可以使用 `InMemoryEventBus`（`EVENT_BUS_BACKEND=memory`），但接口必须一致。

## 5.3 新增 `sinan/services/redis.py`

新增：

```text
sinan/services/redis.py
```

实现：

```python
create_redis()
close_redis()
get_redis()
```

统一管理连接池，不要在每个服务中重复创建 Redis client。

## 5.4 修改 `sinan/api/routes/generate.py`

订阅逻辑改为：

```text
读取 Last-Event-ID 或 cursor
  → replay(cursor 之后的事件)
  → subscribe(cursor)
  → 收到 completed/error/cancelled/awaiting_confirmation 后关闭
```

兼容：

```text
Last-Event-ID header
cursor query parameter
```

## 5.5 对齐事件类型

基础事件至少包含：

```text
session_init
step
gate_passed
code_start
code_delta
code_snapshot
code_stream_end
verify_start
verify_result
fix_start
fix_applied
skill_running
skill_result
knowledge_source
awaiting_confirmation
completed
error
cancelled
```

每类事件明确：

- data 字段；
- 是否持久化；
- 是否可回放；
- 是否终止 SSE；
- 是否改变 Session 状态。

## 验收标准

必须测试：

1. 客户端在任务开始前连接，能收到全部事件；
2. 客户端中途断线，携带 Last-Event-ID 后不丢事件；
3. 任务完成后再连接，能收到 completed；
4. 两个客户端同时订阅，互不消费对方事件；
5. 服务重启后事件仍可回放；
6. completed/error/cancelled 只终止当前 SSE，不影响历史查询。

## 实施结论（2026-08-17，代码已落地）

改动文件：

```text
sinan/models/events.py              新增：GenerationEvent、事件名常量、TERMINAL_EVENTS、data 构造器
sinan/services/generation_event_bus.py  重写：RedisEventBus + InMemoryEventBus，publish/replay/subscribe/get_last_event_id/close/trim
sinan/services/redis.py             新增 create_redis()，get_redis() 委托它保证单一入口
sinan/config/settings.py            新增 SSE 分区与 redis_max_connections
sinan/api/routes/generate.py        Last-Event-ID/cursor → replay → subscribe → 终止事件关闭；新增 session_init
sinan/services/generation_runner.py 事件名换为公共契约（step/fix_applied/verify_result/completed/error/cancelled）
sinan/agents/coder.py               新增 code_start / code_stream_end，code_delta 带 accumulated_len
sinan/api/app.py                    启动时 create_redis()
```

关键设计决定：

- 用 Redis List + INCR 而非 Stream，理由见 5.2 的说明；
- 删除 `publish_done` 与 `_SENTINEL`：终止语义改由事件名承载。哨兵无法持久化，保留它会导致"重连后 SSE 永不结束"；
- `publish` 保留 `(session_id, event_type, data)` 三参数形态，`job_id`/`marker` 走关键字，避免全部调用点改签名；
- 顺带修掉一处既有 bug：`verify_result` 原先嵌在 `iteration > 0` 分支内，零修复时客户端收不到任何验证结果。

遗留项（记录在 `docs/compatibility/event-matrix.md` 的"未对齐"）：

- 取消事件名与参考不同（参考用 `error` 承载取消）；
- `quality_score` 恒为 `0.0`，待 Step 7 扩展 gates/verifier；
- `gate_passed`、`code_snapshot`、`verify_start`、`fix_start`、`awaiting_confirmation`、`chat`、`skill_*`、`knowledge_source` 只固化了协议常量，发布点分别属于 Step 7/8/12；
- 上述 6 条验收标准尚未执行黑盒验证，需在 Step 15 与参考项目做 SSE 原文对照。

运行前置：事件总线默认硬依赖 Redis。本地无 Redis 时必须设 `EVENT_BUS_BACKEND=memory`，否则第一条 `session_init` 就会连接失败。

---

# Step 6：重建数据库模型和迁移

## 目标

从当前三张简化表升级为原项目的职责分离模型。

## 6.1 修改 `sinan/models/enums.py`

补充原项目状态：

```python
class PipelineState(str, Enum):
    INIT = "init"
    INGESTION = "ingestion"
    ANALYSIS = "analysis"
    USER_CONFIRM = "user_confirm"
    DESIGN = "design"
    GENERATION = "generation"
    VALIDATION = "validation"
    PREVIEW = "preview"
    USER_REVIEW = "user_review"
    DELIVERED = "delivered"
    FAILED = "failed"
```

补充 Job 状态：

```text
pending
running
waiting
completed
failed
cancelled
```

补充 Page 状态：

```text
draft
preview
published
archived
```

## 6.2 修改 `sinan/models/tables.py`

最终至少具备：

```text
gen_session
gen_session_step
generation_job
generation_artifact
page
page_version
attachment
skill_definition
page_template
```

当前 `GenSession` 和 `PageVersion` 可以保留一段时间作为兼容层，但所有新业务应逐步转到新模型。

## 6.3 修改 `sinan/models/database.py`

不要长期依赖启动时自动 `create_all()` 作为生产迁移方式。

建议：

1. 开发阶段暂时保留 `create_all()`；
2. 新增 Alembic；
3. 为每一步模型变化生成 migration；
4. 测试空数据库升级；
5. 测试旧数据库升级；
6. 测试回滚或至少测试备份恢复。

## 6.4 新增迁移目录

```text
alembic.ini
alembic/
  env.py
  versions/
```

## 验收标准

- 空数据库能完整初始化；
- 旧三表数据可以迁移；
- Session、Job、Page、Version 关联正确；
- PageVersion 不再承担 Page 主表职责；
- Artifact 可以保存中间产物；
- 查询不会跨用户泄露数据。

## 实施结论（2026-08-17，代码已落地）

落地方式与 6.3/6.4 的原计划不同：**不引入 Alembic，改为库级隔离**。新建空库 `sinan_v2`，
本分支把 `settings.db_name` 指过去，由 `create_all()` 建全部新表；旧库 `sinan` 原样保留，
Step 5 及之前的分支切回去即可正常运行。学习型项目没有需要保住的存量数据，
迁移脚本、数据回填和 downgrade 的成本大于收益。

改动文件：

```text
sinan/config/settings.py            db_name → sinan_v2；redis_db → 1（按分支隔离库与事件键）
sinan/models/enums.py               新增 PipelineState(11 态)/JobStatus/PageSource；SessionStatus 改参考取值；PageStatus 增 preview
sinan/models/tables.py              9 张表：GenSession/GenSessionStep/GenerationJob/GenerationArtifact/Page/PageVersion/Attachment/SkillDefinition/PageTemplate
sinan/services/page_store.py        save() 单事务 upsert page + 写 page_version 快照 + 推进 current_version；新增 get_page/publish
sinan/services/session_store.py     create() 写 status=active / pipeline_state=init / title / attachments
sinan/services/generation_runner.py 4 处状态写入改字符串取值并带 pipeline_state；删除死代码 _save_page
sinan/api/routes/pages.py           页面级状态从 Page 主表读，版本级只返回快照字段
sinan/api/routes/preview.py         同上；版本详情返回 content_hash
sinan/api/routes/session.py         status/pipeline_state 直接返回字符串
sinan/api/routes/audit.py           同上
```

关键设计决定：

- 所有 status 列统一 `String(32)`，与参考一致。数据库 ENUM 每加一个状态就要 ALTER，Step 7/8 还会继续扩状态；取值约束交给 Python 侧的 `str, Enum`；
- `GenSession.status` 采用参考取值（active/paused/…），旧的 pending/running 语义下沉到 `GenerationJob.status` 与新增的 `pipeline_state` 列。新库无存量数据，一次切到位；
- `page` 成为主表，`page_version` 卸掉 `status`/`owner`/`updated_at`，变成不可变快照；
- `PageVersion.html_content` 保留、`bos_path` 可空：Step 9 才接对象存储，本 Step 只把参考的列位打出来；
- `GenerationArtifact`/`Attachment` 的 `metadata` 列以属性名 `meta` 映射，因为 `metadata` 是 SQLAlchemy 声明式保留属性名；
- `attachment` 表参考项目并不存在（参考存在 `generation_session.attachments` JSON），本 Step 只建表不切流量，避免双写不一致；
- 不建 `sys_user`/`buddy_profile`：认证 Step 3 已定"暂不实现"，buddy 与页面生成无关。

遗留项（记录在 `docs/compatibility/storage-matrix.md` 与 `state-matrix.md`）：

- 旧库数据未迁移，`sinan` 库的历史 Session/PageVersion 在新库不可见；
- 无迁移工具，后续模型变更仍需重建库，有真实数据后必须补 Alembic；
- `generation_artifact`/`attachment`/`skill_definition`/`page_template` 只建表，无写入点（Step 7/9/11/12）；
- `pipeline_state` 只有 init/analysis/delivered/failed 四个写入点，中间阶段待 Step 7/8；
- `gen_session.attachments` 恒为 `[]`：`create_or_get()` 未透传 attachments，runner 仍从 `job.request_payload` 读；
- 取消仍落 `failed` + `error_message="cancelled by user"`，参考无 cancelled 会话态，等价性待 Step 15；
- `generation_job_store.py` 仍用裸字符串常量，未收敛到 `JobStatus`；
- `next_version()` 与 `save()` 非原子，同 marker 并发生成会撞 `uk_marker_version`（既有行为）；
- 「查询不跨用户泄露」只做到结构就绪（`page.owner`、`gen_session.user_id` 索引），实际过滤依赖认证，当前 `auth_mode="none"` 无法验证，待 Step 3/15。

运行前置：新库需先手工创建 —— `CREATE DATABASE sinan_v2 CHARACTER SET utf8mb4;`，
且 `.env` 中不能出现 `DB_NAME`/`REDIS_DB`（env 优先级高于 settings 默认值，会盖掉分支隔离）。

---

# Step 7：对齐 Native LangGraph 和 Harness

## 目标

先完整复现原项目的传统生成路径，不引入 Claude Code、Opencode 和 Skill。

## 7.1 扩展 `sinan/agents/state.py`

当前状态过于简单，需要扩展为：

```python
class GenerationState(TypedDict, total=False):
    session_id: str
    job_id: str
    marker: str
    user_id: str

    user_input: str
    attachments: list
    datasources: list

    intent: dict | None
    requirement_doc: dict | None
    analysis_output: dict | None
    design_doc: dict | None
    code: str | None
    code_files: list[dict]
    code_hash: str | None

    pipeline_state: str
    status: str
    gate_reports: list[dict]
    contract_errors: list[dict]
    verification_result: dict | None

    fix_round: int
    max_fix_rounds: int
    fix_history: list[dict]

    messages: list[dict]
    history_messages: list[dict]
    user_confirmed: bool | None
    iteration_feedback: str | None

    template_id: str | None
    template_code: str | None
    skill_context: dict | None
    knowledge_context: dict | None
```

## 7.2 新增 `sinan/agents/router.py`

参考：

```text
page/agents/router.py
page/agents/intent_classifier.py
```

实现意图：

```text
create
modify
template
data_query
chat
```

并提取：

```text
page_type:
dashboard
report
analysis
custom

data_source:
excel
system
api
mock
static
```

## 7.3 修改 `sinan/agents/graph.py`

当前图只有：

```text
analyze → design → code → verify → fix
```

改成至少包含：

```text
route
  → ingestion
  → analysis
  → gate_analysis
  → user_confirm
  → design
  → gate_design
  → generation
  → gate_generation
  → validation
  → repair
  → preview
  → completed
```

不同意图进入不同分支：

```text
chat     → chat_response
create   → full_pipeline
modify   → iteration_router
template → template_pipeline
data_query → skill/data pipeline
```

## 7.4 修改 `sinan/models/contracts.py`

当前 Contract 只检查：

```text
requirements 字符串
design 字符串
HTML 是否有 doctype/html/body
```

参考原项目增加：

```text
IngestionInput
IngestionOutput
NormalizedRequirement
AnalysisOutput
FunctionalModule
DesignOutput
ComponentNode
GenerationOutput
CodeFile
ValidationIssue
ValidationOutput
RepairRecord
RouteDecision
```

代码输出不要只使用一个 HTML 字符串，改成：

```python
class CodeFile(BaseModel):
    path: str
    content: str
    language: str
    role: str

class GenerationOutput(BaseModel):
    files: list[CodeFile]
    entry_point: str = "index.html"
    dependencies: list[dict] = Field(default_factory=list)
```

## 7.5 修改 `sinan/harness/state_machine.py`

让它真正成为运行时的唯一状态转移来源，不要只定义静态字典而不接入。

每次状态变化必须：

1. 校验当前状态是否允许转移；
2. 写入 Session；
3. 写入 Job；
4. 写入事件；
5. 保存 checkpoint；
6. 保存 Artifact；
7. 触发下一节点。

## 7.6 修改 `sinan/harness/gates.py`

Gate 决策扩展为：

```text
proceed
retry
fix
block
wait_user
```

Gate 输出必须包含：

```python
{
    "gate": "...",
    "step": "...",
    "decision": "...",
    "passed": True,
    "score": 0.9,
    "issues": [],
    "timestamp": "...",
}
```

## 7.7 新增或扩展验证器

```text
sinan/harness/validators/requirement.py
sinan/harness/validators/template.py
sinan/harness/validators/data.py
sinan/harness/validators/syntax.py
sinan/harness/validators/render.py
sinan/harness/validators/security.py
sinan/harness/validators/accessibility.py
```

统一输出：

```python
class ValidationIssue(BaseModel):
    issue_id: str
    severity: str
    category: str
    description: str
    location: str | None
    suggestion: str | None
```

## 验收标准

固定同一个 Prompt，比较两个项目：

- Router 结果；
- Analysis 字段；
- Design 字段；
- Code 产物；
- Validation Issue；
- Gate 决策；
- 修复轮数；
- 最终质量分数；
- 事件顺序；
- Session 状态。

## 实施结果（Step 7 落地后回填）

实际实现以参考源码为准，与本节原始设计有 4 处出入 —— 原设计比参考**更激进**，照字面实现反而会偏离基线：

1. **7.3 的 13 个节点不存在。** 参考 `page/agents/graph.py:47-61` 只有 6 个节点
   （router / analyst / designer / coder / verifier / fixer）+ 2 条条件边。
   `ingestion / analysis / design / generation / validation` 是节点写进 state 的 `pipeline_state`
   字符串，不是节点；gate 与 contract 校验由 `page/harness/orchestrator.py:wrap_node` 装饰器
   在每个节点执行后统一跑。因此 sinan 删掉了 `gate_analyze/gate_design/gate_code/gate_verify`
   四个独立门禁节点，改用 `harness/orchestrator.wrap_node`（5 个业务节点包装，fixer 不包装）。
   `preview` / `completed` 也不是节点，参考同样没有。
2. **7.5 的「运行时唯一状态转移来源」参考侧也未实现。** `page/harness/state_machine.py` 的
   `PipelineStateMachine` 全仓零 import。sinan 只把转移表改成与参考 1:1（11 态、14 条带
   condition 的三元组），运行时接入记为**两边共同缺口**，留 Step 15，不自造参考没有的强校验。
3. **7.7 的 `security.py` / `accessibility.py` 本 Step 不建。** 参考只有 5 个 validator
   （requirement / template / data / syntax / render），`IssueCategory` 里预留了 `security` / `a11y`
   但无实现。sinan 保持一致。
4. **`chat` 分支不在图里。** 参考在 API 路由用 `classify_intent` 拦截
   （`page/api/routes/generate.py:180`），属 Step 8，本 Step 不做。

按 7.6 要求增加的 `decision` 字段是 sinan 增量：参考的门禁报告只有
`gate/step/passed/score/auto_confirmed/requires_user`（`page/harness/orchestrator.py:119-126`），
用 `passed + requires_user` 表达决策。sinan 额外输出 `decision/issues/timestamp`，已记入
`docs/compatibility/state-matrix.md`。

其他与参考的**已知差异**（全部记入兼容矩阵）：

- 无 `harness_checkpoint` 表与 BOS artifact，checkpoint 仍靠 LangGraph `MemorySaver`（Step 9 收口）；
- `RenderValidator` 只采集 JS 运行时错误，不做参考的 Vision LLM 28 项视觉检查，且
  `render_validation_enabled` 默认 False —— **Step 15 黑盒对照前必须开启并装 playwright**，
  否则 sinan 侧 issue 数、修复轮数、`quality_score` 会系统性偏优；
- `analysis_delta` / `design_delta` 流式事件是 sinan 独有（参考 analyst/designer 非流式）；
- `fix_start` / `fix_applied` 由 `agents/fixer.py` 每轮发布（参考 native 路径不发这两个事件）；
- analyst 挂起时 `pipeline_state` 写 `user_confirm`（参考写 `analysis`）；
- `step` 事件取值改为参考节点名 `router/analyst/designer/coder/verifier/fixer`（前端需同步）。

新增/重写文件：`agents/router.py`、`harness/orchestrator.py`、`harness/contracts.py`、
`harness/validators/{requirement,template,data,syntax,render}.py`，
重写 `models/contracts.py`（13 个结构化契约 + `compute_quality_score`）、`agents/state.py`
（`PageGenState` → `GenerationState`）、五个 agent、`harness/{gates,state_machine}.py`、`agents/graph.py`；
`generation_job_store` 新增 `mark_waiting()`；`harness/validators/browser_validator.py` 保留但已无引用点。

---

# Step 8：对齐用户确认、取消、恢复和多轮修改

## 目标

让 `sinan` 从单轮自动生成器变成可交互的页面创作流程。

## 8.1 新增请求模型

在 `sinan/models/contracts.py` 增加：

```python
class SessionConfirmRequest(BaseModel):
    confirmed: bool = True
    feedback: str | None = None

class SessionIterateRequest(BaseModel):
    feedback: str
    mode: str | None = None

class SessionAbortRequest(BaseModel):
    reason: str | None = None
```

## 8.2 新增 `sinan/services/session_action_service.py`

新增：

```text
sinan/services/session_action_service.py
```

职责：

```python
confirm(session_id, user_id, request)
iterate(session_id, user_id, request)
abort(session_id, user_id, reason)
resume(session_id, user_id)
```

这些函数不能直接在路由里修改几张表，而应该：

```text
校验权限
  → 校验当前状态
  → 创建 Action Job
  → 更新 Session
  → 发布事件
  → 由 Supervisor 执行
```

## 8.3 新增 `sinan/harness/iteration_router.py`

参考：

```text
page/harness/iteration_router.py
```

根据反馈决定：

```text
design
generation
direct_edit
chat
```

输出：

```python
RouteDecision(
    target_step="generation",
    reason="只修改颜色",
    change_scope="partial",
    affected_modules=["theme"],
    preserved_modules=["table", "header"],
)
```

## 8.4 新增 `sinan/agents/direct_editor.py`

对于以下修改，不要重新执行完整流程：

```text
改颜色
改文案
调整间距
隐藏一个模块
修改某个图表标题
```

Direct Editor 读取：

```text
当前页面
用户反馈
最近一次验证结果
受影响模块
```

只生成局部修改，保存新 PageVersion。

## 验收标准

必须支持：

- Analysis 后进入 `awaiting_confirmation`；
- confirmed=true 继续生成；
- confirmed=false 停止并保存反馈；
- feedback 进入重新分析或局部修改；
- abort 后任务不能继续运行；
- resume 后从 checkpoint 继续；
- 修改已有页面会生成新版本；
- 旧版本内容不变。

---

# Step 9：对齐附件、Artifact、Storage 和 BOS

## 目标

从“数据库里保存一个 HTML 字符串”升级为“可管理的多文件页面产物”。

## 9.1 新增 `sinan/services/storage.py`

抽象接口：

```python
class StorageBackend(Protocol):
    async def put(self, key: str, content: bytes, content_type: str | None = None) -> str:
        ...

    async def get(self, key: str) -> bytes:
        ...

    async def delete(self, key: str) -> None:
        ...

    async def exists(self, key: str) -> bool:
        ...

    async def signed_url(self, key: str, expires: int = 3600) -> str:
        ...
```

实现两个后端：

```text
sinan/services/local_storage.py
sinan/services/bos_storage.py
```

先使用 LocalStorage 完成测试，再接 BOS。

## 9.2 新增 `sinan/services/artifact_store.py`

实现：

```python
save_artifact(...)
get_artifact(...)
list_artifacts(session_id)
save_code_snapshot(...)
save_validation_report(...)
save_skill_output(...)
```

Artifact 保存策略：

```text
小 JSON → 数据库
大文本/二进制 → StorageBackend
数据库只保存 URI、hash、metadata
```

## 9.3 修改 `sinan/services/data_service.py`

当前主要针对 Excel。扩展为：

```text
Excel
CSV
图片
ZIP
文本
PDF/文档（如果原项目支持）
```

每个附件处理结果统一为：

```json
{
  "file_id": "...",
  "filename": "...",
  "content_type": "...",
  "storage_uri": "...",
  "sha256": "...",
  "parse_type": "excel",
  "parsed": {},
  "status": "ready"
}
```

## 9.4 修改 `sinan/services/session_store.py`

不要继续把完整附件内容塞入 Session JSON。改为：

```text
Session 只保存 attachment_id 列表
Attachment 保存文件和解析结果
Artifact 保存生成过程中的上下文快照
```

## 验收标准

- 上传原始文件后可以重新下载；
- 生成任务重启后仍能读取附件；
- 同一个文件按 hash 去重；
- 文件解析信息可回放；
- 页面版本支持多个文件；
- `index.html` 是明确入口；
- PageVersion 能保存文件列表、大小、hash；
- 本地 Storage 和 BOS Storage 使用相同接口。

---

# Step 10：对齐页面、版本、预览、发布和托管

## 目标

让页面产物不只可以生成，还可以预览、发布、托管和回滚。

## 10.1 修改 `sinan/api/routes/preview.py`

当前主要按 marker 返回 HTML。扩展为：

```text
GET /api/page/preview/{marker}
GET /api/page/preview/{marker}/v/{version}
GET /api/page/{marker}/versions
GET /api/page/{marker}/files/{path}
```

处理逻辑：

```text
查询 Page
  → 选择 current_version 或指定 version
  → 从 Artifact/Storage 读取 entry_file
  → 处理静态资源路径
  → 返回页面或重定向到预览地址
```

## 10.2 新增 `sinan/api/routes/hosting.py`

支持：

```text
POST /api/page/hosting
POST /api/page/hosting/zip
GET  /api/page/hosting/{marker}
POST /api/page/{marker}/publish
POST /api/page/{marker}/unpublish
```

## 10.3 新增 `sinan/services/page_service.py`

实现：

```python
create_page(...)
create_version(...)
get_page(...)
list_versions(...)
publish_page(...)
unpublish_page(...)
rollback_version(...)
```

页面状态必须与版本状态分离：

```text
Page.status
Page.current_version
Page.published_version
PageVersion.status
```

## 10.4 新增 `sinan/services/security.py`

ZIP 和页面安全处理至少包括：

- 禁止 `../`；
- 禁止绝对路径；
- 限制文件扩展名；
- 限制单文件大小；
- 限制总解压大小；
- 限制文件数量；
- 扫描危险脚本；
- 扫描外部请求；
- 不允许覆盖服务目录；
- 不允许访问宿主机敏感路径。

## 验收标准

- 指定版本可以稳定预览；
- 发布只发布指定版本；
- 回滚只改变 current/published 指针，不删除历史版本；
- 非法 ZIP 被拒绝；
- 资源路径不能穿越；
- 未授权用户不能访问私有页面；
- 页面发布后地址和原项目格式一致。

---

# Step 11：对齐页面模板和 Prompt Template

## 目标

实现原项目的模板分支，避免所有请求都走自由生成。

## 11.1 新增 `sinan/services/template_store.py`

实现：

```python
list_templates(...)
get_template(template_id)
save_template(...)
update_template(...)
disable_template(...)
```

## 11.2 新增路由

```text
sinan/api/routes/template.py
sinan/api/routes/prompt_template.py
```

对齐：

```text
GET  /api/page/templates
GET  /api/page/templates/{template_id}
POST /api/page/templates
PATCH /api/page/templates/{template_id}
GET  /api/page/prompt-templates
```

## 11.3 修改 `sinan/api/routes/generate.py`

处理：

```text
req.prompt_template_id 非空
  → 查询 Prompt Template
  → 如果有效，直接进入模板生成
  → 如果不存在，按原项目规则返回错误或 fallback
```

对于 `template_id`：

```text
加载模板文件
  → 放入 GenerationState.template_code
  → Coder/Runtime 以模板为基准
  → 验证模板保留结构
```

## 验收标准

- 指定有效模板时走模板分支；
- 指定无效模板时行为与原项目一致；
- 模板生成不会无故丢失模板固定模块；
- 页面版本记录 template_id；
- 模板状态和权限有效。

---

# Step 12：对齐 Skill、知识库和数据源

## 目标

实现原项目的业务扩展能力，但先建立通用框架，再接具体业务 Skill。

## 12.1 新增 Skill Registry

新增：

```text
sinan/services/skill_registry.py
sinan/services/skill_package.py
sinan/api/routes/admin_skills.py
```

实现：

```python
list_skills(...)
get_skill(skill_key)
install_skill(...)
enable_skill(...)
disable_skill(...)
update_skill(...)
sync_enabled_skills(...)
```

数据库模型：

```text
SkillDefinition
```

状态：

```text
enabled
disabled
installing
failed
```

## 12.2 新增运行时工具注册表

新增：

```text
sinan/runtime/tool_registry.py
```

职责：

```text
列出可用 Skill
按场景过滤 Skill
解析显式 skill_keys
按 Prompt 路由 Skill
执行 Skill
规范化 Skill 输出
```

## 12.3 新增知识库服务

新增：

```text
sinan/services/knowledge_context.py
sinan/services/document_parser.py
```

处理：

```text
knowledge_sources URL
  → 校验
  → 抓取/读取
  → 解析
  → 限长
  → 清洗
  → 写入 Knowledge Artifact
  → 注入 GenerationState
```

如果需要用户补充链接：

```text
skill_link_required
  → Session.awaiting_confirmation
  → SSE awaiting_confirmation
  → 用户补充
  → Action Job 继续
```

## 12.4 对齐数据源

扩展：

```text
sinan/models/contracts.py
sinan/services/data_service.py
sinan/agents/state.py
```

支持：

```text
api
static
database
file
mock
```

每个数据源都应有：

```text
schema
sample_data
fetch method
timeout
error policy
```

## 12.5 最后接具体业务 Skill

建议顺序：

1. 一个最简单的 mock Skill；
2. 一个静态数据 Skill；
3. 一个真实数据查询 Skill；
4. GPU delivery；
5. PL analysis；
6. ku-doc；
7. UGate Token 相关 Skill。

不要一开始把所有外部 Skill 都接进来。

## 验收标准

- 显式 `skill_keys` 能强制选择 Skill；
- Prompt 能路由到匹配 Skill；
- Skill 运行事件可通过 SSE 观察；
- Skill 输出可以保存为 Artifact；
- Skill 失败可以进入等待确认或失败；
- Skill 不会读取其他用户的数据；
- 知识库上下文能传递到生成 Runtime。

## 实施结论（2026-08-25，代码已落地）

本 Step 有意不接参考项目的外部设施（BOS zip 包、UGate/UUAP token、PL/PALO/ku 等真实业务
接口），全部用本地文件替代——目的是学习 agent 的 Skill 机制，而不是复刻内网集成。

### 落地清单

新增：

```text
sinan/services/skill_package.py       # 本地包发现与 SKILL.md 解析（替代 zip 下载解压）
sinan/services/skill_registry.py      # skill_definition 读写门面 + 启动同步
sinan/api/routes/admin_skills.py      # 6 个端点（参考 5 个 + GET /local）
sinan/runtime/tool_registry.py        # 选择 / 过滤 / 路由 / 执行 / 归一化
sinan/services/document_parser.py     # md/txt/json/html/csv/xlsx → 纯文本
sinan/services/knowledge_context.py   # 校验→读取→解析→限长→清洗→Artifact→注入
sinan/agents/skill_agent.py           # 图节点 skill
sinan/skills/mock-metrics/            # 12.5 第 1 步：mock Skill
sinan/skills/static-sales/            # 12.5 第 2 步：静态数据 Skill
```

修改：`settings.py`（Skill/知识库/数据源配置段）、`models/events.py`（4 个事件 data 构造器 +
`SKILL_LINK_REQUIRED`）、`models/contracts.py`（`DataSourceConfig` 扩展、confirm/iterate 请求体
加补链接字段）、`agents/state.py`（11 个 Skill/知识库/数据源键）、`agents/graph.py`
（`router → skill → analyst` + `_after_skill`）、`agents/analyzer.py` / `agents/coder.py`
（注入 `external_knowledge` 与 `datasource_context`）、`services/data_service.py`
（`parse_datasource_ref` + `resolve_datasources`）、`services/generation_runner.py`
（入参注入、数据源取数、缺链接挂起分支、`step_labels` 加 skill）、`api/app.py`
（注册路由 + 启动同步）。

### 关键设计与差异

1. **包来源**：`settings.skills_dir`（默认 `./sinan/skills`）下一个目录即一个 Skill，
   `skill_key = 目录名`，`SKILL.md` frontmatter 提供 `name/description/output_type/keywords/
   requires_link`。相对路径按**项目根**解析（`_PROJECT_ROOT = parents[2]`），与参考
   `page/services/skill_package.py:18` 同思路，不受启动工作目录影响。
2. **执行协议**：子进程 `sys.executable handler.py`，stdin 收
   `{prompt, session_id, marker, params}`，stdout 回 `{ok, content, error?}`；
   超时 `skill_timeout_seconds`(60)，环境只透传 `PATH/LANG/LC_ALL/PYTHONPATH/HOME`，
   不注入任何凭证（参考注入 UGATE_TOKEN / PL_API_*）。stdout 非 JSON 时整段当纯文本兜底。
3. **选择顺序**：显式 `skill_keys` → （可选 LLM 路由，默认关）→ 关键词路由。
   参考的 auto 路由被硬关（`codegen_engine.py:508`），sinan 打开关键词路由，
   否则验收标准第 2 条无法验证。
4. **缺链接挂起**：`skill_link_required` 事件 + `status=awaiting_confirmation`，
   `_after_skill` 让图在 skill 节点后 END，runner 走既有挂起分支（Session paused / Job waiting）。
   用户 confirm 时带 `link` / `knowledge_sources` 续跑。**sinan 增量**：`user_confirmed=True`
   时跳过链接门，避免"确认但仍不给链接"导致无限挂起。
5. **失败策略**：普通 Skill 失败不阻断（`skill_context.failed` + `skill_result{success:false}`），
   与参考一致；只有缺链接才挂起。
6. **知识库**：本地文件优先（`knowledge_dir` 前缀校验防穿越），HTTP 默认关闭
   （`knowledge_allow_http=False`），开启后保留 SSRF 校验（拒 localhost/私网/link-local）与 1MB 上限。
   单篇限 50000 字符、合并限 120000 字符，落 `artifact_type="knowledge"`。
7. **数据源**：请求字段仍是 `list[str]`（对齐线上协议），由 `parse_datasource_ref` 解析成
   `DataSourceConfig`；支持 `mock:` / `file:` / `static:` / `api:` / 裸 URL，`db:` 显式返回
   unsupported。每条结果带 `data_schema` / `sample_data` / `timeout` / `error_policy`。

### 已验证（本地自检脚本，跑完即删）

- 本地包发现与解析：2 个包 `enabled`，keywords 与 handler 路径正确；
- 子进程执行：两个 Skill 均 `ok=true`，输出为结构化 JSON；
- 路由：`用模拟数据做个收入看板` → `mock-metrics`（命中 `模拟数据`）、
  `做一个区域销售额看板` → `static-sales`、`做个时间页面` → 不选；
- 显式选择：命中记 `explicit`，未安装 key 记 `explicit_missing`；
- 缺链接：无源时挂起、有源时放行、`user_confirmed=True` 时不再拦；
- 知识库：合法本地文件成功；越界 / 缺失 / HTTP 禁用三种失败都有明确 error 且不阻断；
- 数据源：`mock` 成功、`db` unsupported、`file` 缺失与越界均明确报错；
- 图编译：节点为 `router/skill/analyst/designer/coder/verifier/fixer` 共 7 个；
- 启动同步：`sync_enabled_skills()` upsert 2 条记录；
- 6 个 admin 端点：200 / 404 / 400 / 422 行为符合预期。

**未验证**：需要真实 LLM key 的整链生成（`POST /api/page/generate` 全程 SSE 原文与最终页面
是否真的用上了 Skill 数据），以及 Skill 输出落 `generation_artifact` 的实际行数——
两者都要跑一次完整生成，留待手动执行。

---

# Step 13：对齐 Claude Code Runtime

## 目标

把生成执行从单一 LangGraph 抽象成 Runtime 接口，并实现原项目的 Claude Code 路径。

## 13.1 新增 Runtime 抽象

新增：

```text
sinan/runtime/base.py
sinan/runtime/events.py
sinan/runtime/registry.py
```

定义：

```python
class RuntimeEvent(BaseModel):
    type: str
    session_id: str
    data: dict

class GenerationRuntime(Protocol):
    async def run(
        self,
        state: dict,
        thread_id: str,
    ) -> AsyncIterator[RuntimeEvent]:
        ...
```

实现：

```text
NativeLangGraphRuntime
ClaudeCodeRuntime
OpencodeRuntime
```

## 13.2 新增 Claude Code 模块

```text
sinan/claude_code/runtime.py
sinan/claude_code/codegen_engine.py
sinan/claude_code/prompt_router.py
sinan/claude_code/tool_registry.py
sinan/claude_code/context.py
```

职责：

- 处理多轮 turn；
- 调用工具；
- 产生 runtime event；
- 保存 code snapshot；
- 调用 Skill；
- 支持 checkpoint；
- 根据已有页面执行增量编辑。

原项目参考：

```text
page/claude_code/runtime.py
page/claude_code/codegen_engine.py
page/claude_code/prompt_router.py
page/claude_code/tool_registry.py
```

## 13.3 修改 `sinan/services/generation_runner.py`

将直接调用 Graph 的代码改为：

```text
根据 mode / settings / prompt 路由 Runtime
  → 执行 Runtime
  → RuntimeEvent 转 SSEEvent
  → 保存 Artifact
  → 更新状态
```

不要让 Runner 了解每个 Runtime 的内部事件格式。

## 验收标准

- Native Runtime 和 Claude Code Runtime 使用统一 Runner；
- Runtime 事件可以统一转换成 SSE；
- Claude Code 生成中断后可恢复；
- 工具调用有事件；
- 生成结果保存为同样的 PageVersion/Artifact；
- 同一个 Prompt 的 Runtime 选择符合原项目规则。

## 实施结论（2026-08-25，代码已落地）

**新增文件：**
- `sinan/runtime/events.py`：`RuntimeEvent` dataclass（对齐 `page/claude_code/events.py`）
- `sinan/runtime/base.py`：`GenerationRuntime` Protocol，`@runtime_checkable`
- `sinan/runtime/native.py`：`NativeLangGraphRuntime`，将 `astream_events v2` 翻译为 `RuntimeEvent` 流
- `sinan/runtime/registry.py`：`RuntimeRegistry`，按 `mode` 路由；未知 mode 降级 native 并 warning
- `sinan/claude_code/__init__.py`：包文件
- `sinan/claude_code/runtime.py`：`ClaudeCodeRuntime`，当前底层为 `NativeLangGraphRuntime`，对齐 `page/claude_code/runtime.py` 接口

**修改文件：**
- `sinan/runtime/__init__.py`：从占位注释改为正式导出 `RuntimeEvent / GenerationRuntime / RuntimeRegistry`
- `sinan/config/settings.py`：在 `# --- Runtime ---` 分组新增 `claude_code_backend: str = "native"`
- `sinan/services/generation_runner.py`：
  - `__init__` 初始化 `RuntimeRegistry`
  - `_run_graph` 改为通过 `RuntimeRegistry.get(mode)` 路由 Runtime，消费 `RuntimeEvent`（`step` / `graph_output`）而非直接调用 `astream_events`

**有意的差异：**
- `ClaudeCodeRuntime` 底层仍是 native 图，未重写 `CodegenEngine` 手动链式调用，因为 sinan 的 LangGraph 图节点已与参考对齐，功能等价
- `NativeLangGraphRuntime.resume()` 返回 `runtime_error` 事件（无 checkpoint store），Step 14 引入真实 checkpoint 时再实现
- skill 节点保留在图中，未下移到 runtime 层（参考做法），Step 14 对照时再评估

---

# Step 14：对齐 Opencode 和 Hybrid Runtime

## 目标

实现原项目的 Opencode 主路径、Native fallback 和 Hybrid 模式。

## 14.1 新增 Opencode 服务

新增：

```text
sinan/services/opencode.py
sinan/services/opencode_context.py
sinan/api/opencode_stream.py
```

实现：

```python
stream_generate(...)
stream_chat(...)
cancel(...)
```

处理：

```text
外部 Runtime 事件
  → 解析
  → 转为 RuntimeEvent
  → 统一送入 Runner
```

## 14.2 修改设置和模式选择

在 `sinan/config/settings.py` 增加：

```text
opencode_enabled
opencode_base_url
opencode_mode
```

模式：

```text
native
opencode
hybrid
auto
```

原项目参考：

```text
page/api/routes/generate.py:88-96
```

## 14.3 实现 fallback

行为：

```text
Opencode 连接失败且没有产生有效回复
  → 保存错误/部分代码
  → 转 Native Runtime

Opencode 已经产生 chat 回复
  → 不重复进入页面生成

Opencode 已经产生部分代码
  → Native Runtime 从部分代码继续
```

这部分必须通过事件和状态测试验证，不能只用异常捕获粗略实现。

## 验收标准

- full opencode 模式与原项目一致；
- hybrid 模式的 code phase 路由一致；
- Opencode 失败可 fallback；
- 已产生 chat 回复时不会重复生成页面；
- 部分代码可以继续生成；
- cancel 能停止外部 Runtime；
- SSE 事件顺序稳定。

---

# Step 15：安全、可观测性和最终兼容验收

## 目标

完成平台化能力，并证明对齐不是“看起来相似”。

## 15.1 安全检查

新增或完善：

```text
sinan/services/security.py
sinan/harness/validators/security.py
sinan/api/routes/hosting.py
```

检查：

- ZIP 路径穿越；
- 绝对路径；
- 解压炸弹；
- 危险扩展名；
- 外部脚本；
- 内联危险代码；
- 外部请求；
- 文件大小；
- 文件数量；
- 资源权限；
- Token 泄露；
- Prompt 注入到工具调用。

## 15.2 可观测性

完善：

```text
sinan/core/logging.py
sinan/api/context.py
sinan/api/routes/trace.py
sinan/services/trace_service.py
```

每次生成至少关联：

```text
trace_id
user_id
session_id
job_id
marker
runtime
attempt
pipeline_state
```

## 15.3 建立兼容性测试目录

```text
tests/compatibility/
├── test_api_paths.py
├── test_request_contracts.py
├── test_response_contracts.py
├── test_auth_behavior.py
├── test_session_lifecycle.py
├── test_job_recovery.py
├── test_sse_replay.py
├── test_event_order.py
├── test_pipeline_state.py
├── test_generation_contracts.py
├── test_user_confirmation.py
├── test_iteration.py
├── test_upload.py
├── test_artifacts.py
├── test_versions.py
├── test_preview.py
├── test_hosting_security.py
├── test_template.py
├── test_skill.py
├── test_knowledge_source.py
├── test_native_runtime.py
├── test_claude_runtime.py
└── test_opencode_runtime.py
```

## 15.4 每个测试都采用“双项目对照”

推荐测试方式：

```text
准备同一个输入
  → 调用原项目
  → 记录 HTTP 响应
  → 记录 SSE 事件
  → 记录数据库状态
  → 记录页面产物 metadata

  → 调用 sinan
  → 记录相同信息

  → 标准化动态字段
  → 比较剩余结果
```

需要标准化的动态字段：

```text
session_id
job_id
trace_id
时间戳
随机 marker
token 数
LLM 具体文本
```

不能标准化掉的行为：

```text
事件名称
事件顺序
状态变化
错误类型
HTTP 状态码
页面版本号
Artifact 类型
是否进入确认
是否触发 fallback
```

## 15.5 最终验收门槛

只有满足以下条件，才能认为达到“行为百分百对齐”：

1. API 路径和方法一致；
2. 请求和响应结构一致；
3. 认证失败行为一致；
4. Session/Job 状态一致；
5. 断线回放一致；
6. 取消、恢复、重试一致；
7. 事件名称和顺序一致；
8. 同一分支选择一致；
9. Page 和 PageVersion 语义一致；
10. Artifact 保存时机一致；
11. 用户确认和多轮修改一致；
12. Skill、模板和知识库分支一致；
13. Runtime fallback 一致；
14. 预览和发布行为一致；
15. 安全拦截行为一致；
16. 所有兼容性测试通过。

---

# 推荐的实际开发节奏

每个 Step 都按照以下循环执行：

```text
1. 阅读原项目对应文件
2. 在 sinan 中新增最小接口
3. 编写单元测试
4. 编写两个项目的黑盒对照测试
5. 实现 sinan
6. 对比响应、状态和事件
7. 修正差异
8. 冻结本 Step 的兼容测试
9. 再进入下一个 Step
```

不要同时修改多个跨层模块。建议每次只完成一个闭环，例如：

```text
先完成“生成 API + Session + SSE”
再完成“Job 恢复”
再完成“用户确认”
再完成“页面版本”
```

---

# 第一阶段建议立即执行的具体任务

如果现在开始实施，建议先做下面五个小任务：

## Task 1：新建兼容矩阵

新增：

```text
docs/compatibility/api-matrix.md
docs/compatibility/event-matrix.md
docs/compatibility/state-matrix.md
```

先不要修改业务代码。

## Task 2：扩展请求模型

修改：

```text
sinan/models/contracts.py
sinan/api/routes/generate.py
```

让请求字段先和原项目一致。

## Task 3：增加 `/api/page/generate`

修改：

```text
sinan/api/app.py
sinan/api/routes/generate.py
```

先实现路径和 SSE 形态兼容，内部仍可暂时使用现有 Runner。

## Task 4：增加 GenerationJob

新增/修改：

```text
sinan/models/tables.py
sinan/services/generation_job_store.py
sinan/services/generation_runner.py
```

把 `asyncio.create_task` 替换为 Job 调度。

## Task 5：把内存 EventBus 抽象出来

修改：

```text
sinan/services/generation_event_bus.py
```

先定义 replay/subscribe 接口，再接 Redis。

---

# 最终架构目标

完成所有 Step 后，`sinan` 的目标架构应接近：

```text
FastAPI API
  → Auth / Request Context
  → Application Services
      → Session Service
      → Job Service
      → Page Service
      → Artifact Service
      → Storage Service
      → Skill Service
      → Template Service
  → Generation Supervisor
      → Native LangGraph Runtime
      → Claude Code Runtime
      → Opencode Runtime
  → Harness
      → Contract
      → Gate
      → Checkpoint
      → Validator
      → Repair
  → Event Bus
      → Redis replay
      → SSE
  → Persistence
      → MySQL
      → Redis
      → LocalStorage/BOS
```

最重要的实施原则是：

> 先对齐外部行为，再对齐内部结构；先完成可恢复任务和事件协议，再扩展 Skill 和 Runtime；每完成一个 Step，就用双项目黑盒测试冻结行为。

