# sinan 与原项目 page 的对齐分析与实施方案

## 一、总体结论

当前 `sinan` 已经完成了原项目最基础的“页面生成主链路”：

```text
用户 Prompt
  → 需求分析
  → 页面设计
  → HTML 生成
  → 页面验证
  → 自动修复
  → 保存页面版本
  → SSE 推送进度
```

但它目前只覆盖了原项目的一小部分。原项目的实际定位不是“LLM 生成 HTML 服务”，而是一个完整的页面生成平台：

```text
认证
  → 会话/任务创建
  → 持久化任务队列
  → Skill / 知识库 / 模板 / 数据源路由
  → Claude Code / Opencode / LangGraph 多运行时
  → Harness 合约与门禁
  → 用户确认与多轮修改
  → Redis 事件回放
  → MySQL 持久化
  → BOS 产物存储
  → 页面预览、版本、发布、托管
```

所以当前项目和原项目的差距，不只是“还少几个文件”，而是任务模型、接口模型、运行时模型和存储模型都还没有完全对齐。

## 二、当前已经对齐的部分

### 1. 基础生成流程已经建立

`sinan` 当前图结构大致为：

```text
analyze
  → gate_analyze
  → design
  → gate_design
  → code
  → gate_code
  → verify
  → gate_verify
  → fix
  → verify
```

对应文件：

- `sinan/agents/graph.py`
- `sinan/agents/analyzer.py`
- `sinan/agents/designer.py`
- `sinan/agents/coder.py`
- `sinan/agents/verifier.py`
- `sinan/agents/fixer.py`

这和原项目传统 LangGraph 链路中的：

```text
router
  → analyst
  → designer
  → coder
  → verifier
  → fixer
```

方向是一致的。

### 2. 已经有基础 Harness 思想

你的项目已经包含：

- Agent 输出 Contract；
- Gate；
- retry；
- fix；
- 最大修复次数；
- 浏览器验证器。

比如 `sinan/models/contracts.py:14` 开始已经定义了分析、设计、代码和验证契约。

原项目也有对应的：

- `page/harness/contracts.py`
- `page/harness/gates.py`
- `page/harness/orchestrator.py`
- `page/harness/checkpoint.py`
- `page/harness/repair.py`
- `page/harness/iteration_router.py`

所以你现在的 Harness 可以视为原项目 Harness 的早期简化版。

### 3. 已经有数据库持久化意识

当前 `sinan` 已经不是纯内存 Demo，定义了：

- `gen_session`
- `gen_session_step`
- `page_version`

位置：

- `sinan/models/tables.py:8`
- `sinan/models/tables.py:40`
- `sinan/models/tables.py:64`

并且已经具备：

- session 状态；
- 当前步骤；
- 修复迭代次数；
- 页面 marker；
- 页面版本；
- 页面内容；
- 错误信息；
- 步骤输入输出；
- Contract 结果；
- Gate 决策；
- token 和耗时统计。

这为后续对齐原项目提供了不错的基础。

### 4. 已经有附件上传和页面版本能力

当前项目已经覆盖：

- Excel 文件解析；
- 数据预览；
- 本地 JSON 保存；
- 页面版本保存；
- 页面版本列表；
- 页面预览。

原项目对应能力更复杂，但你的抽象方向是对的。

### 5. 已经开始考虑真实浏览器验证

`sinan/harness/validators/browser_validator.py` 已经尝试检查：

- JavaScript 错误；
- 页面 body 内容；
- ECharts 实例。

这比只检查 HTML 字符串更接近原项目的实际质量验证方向。

## 三、最重要的差异总览

| 领域 | 当前 `sinan` | 原项目 `page` | 差异等级 |
|---|---|---|---|
| API 前缀 | `/api/v1/...` | `/api/page/...` | P0 |
| 生成接口形态 | POST 返回 JSON，GET 建立 SSE | POST 本身返回 SSE | P0 |
| 认证 | `user_id` 由请求体传入，默认 anonymous | UUAP/Web Auth/UGate Token | P0 |
| 任务执行 | `asyncio.create_task` | DB Job + Supervisor + Lease | P0 |
| 任务恢复 | 不支持 | 支持服务重启后恢复 | P0 |
| SSE | 进程内 `asyncio.Queue` | Redis 持久化、事件 ID、回放 | P0 |
| 多实例部署 | 不可靠 | Redis 支持多实例 | P0 |
| 运行时 | 单一 LangGraph | LangGraph + Claude Code + Opencode | P0 |
| Skill | 没有完整 Skill 路由 | Skill Registry、Skill 包、动态执行 | P0 |
| 知识库 | 没有 | 知识库链接、文档解析和上下文注入 | P1 |
| 模板 | 基本没有 | 页面模板、Prompt 模板 | P1 |
| 用户确认 | 状态字段存在，但流程未完整接通 | 正式的 awaiting_confirmation 状态和接口 | P0 |
| 多轮修改 | 基本没有 | session 恢复、反馈路由、局部重生成 | P0 |
| 页面模型 | `PageVersion` 为核心 | `Page` + `PageVersion` + Artifact | P0 |
| 产物存储 | HTML 直接存数据库 | BOS 文件、hash、入口文件、文件列表 | P0 |
| 页面发布 | 基本没有 | 发布、托管、ZIP 安全扫描 | P1 |
| 附件 | 主要是 Excel | Excel、CSV、图片、BOS 原始文件、解析上下文 | P1 |
| 验证器 | 基础 HTML/浏览器验证 | 需求、模板、数据、语法、渲染、安全、无障碍 | P1 |
| 日志 | 控制台日志 | 文件日志、访问日志、trace_id、用户上下文 | P2 |
| 异常 | `SinanError` 未形成全局处理 | PageError、AuthenticationError 全局转换 | P1 |
| Skill 管理 | 没有 | 管理接口、启停、安装、同步 | P1 |
| 用户/Buddy | 没有 | 用户、Buddy、会话历史 | P2 |
| Trace | 没有 | Trace 查询接口和运行记录 | P2 |

## 四、API 层没有对齐的地方

### 1. 路径不一致

当前项目注册的是：

```text
GET  /health
POST /api/v1/generate
GET  /api/v1/generate/{session_id}/stream
GET  /api/v1/generate/{session_id}/audit
POST /api/v1/data/upload
GET  /api/v1/page/{marker}
```

位置：

- `sinan/api/app.py:20-27`

原项目的路由主要使用：

```text
/api/page/...
```

例如：

```text
GET  /api/page/health
GET  /api/page/ready
POST /api/page/generate
GET  /api/page/...
```

原项目生成路由：

- `page/api/routes/generate.py:47`
- `page/api/routes/generate.py:67`

如果目标是“百分百一致”，路径必须以原项目为准。当前 `/api/v1` 是重构过程中的新设计，和原项目不兼容。

建议先建立一份 API 对照表：

```text
原项目路径                  sinan 当前路径                  对齐状态
/api/page/generate           /api/v1/generate               不一致
/api/page/health             /health                        不一致
/api/page/ready              无                             缺失
/api/page/preview/{marker}   /api/v1/page/{marker}          不一致
...
```

然后逐项迁移。

### 2. 生成接口的交互模型完全不同

当前项目：

```text
POST /api/v1/generate
  → 返回
{
  "session_id": "...",
  "status": "running"
}

GET /api/v1/generate/{session_id}/stream
  → 建立 SSE
```

位置：

- `sinan/api/routes/generate.py:35-43`
- `sinan/api/routes/generate.py:46-56`

原项目：

```text
POST /api/page/generate
  → 直接返回 SSE
```

位置：

- `page/api/routes/generate.py:67-78`

原项目的 POST 请求会：

1. 创建或复用 job；
2. 启动任务；
3. 直接订阅并返回 SSE；
4. 重放之前已经产生的事件；
5. 持续监听后续事件；
6. 在 completed、error、chat、awaiting_confirmation 时结束。

对应逻辑：

- `page/api/routes/generate.py:67-78`
- `page/api/routes/generate.py:108-125`

这意味着当前前端如果按照原项目方式调用，无法直接使用 `sinan`。

建议把生成流程改为：

```text
POST /api/page/generate
  → 创建/复用任务
  → 确保任务运行
  → 返回 SSE
```

如果希望保留当前 JSON + GET SSE 方式，可以暂时保留兼容接口，但原项目兼容接口必须优先实现。

### 3. 请求模型缺少大量字段

当前请求模型只有：

```python
class GenerateRequest(BaseModel):
    prompt: str
    user_id: str = "anonymous"
    attachments: list[dict] = []
```

原项目请求模型包含：

- `prompt`
- `session_id`
- `marker`
- `attachments`
- `preset`
- `template_id`
- `prompt_template_id`
- `datasources`
- `knowledge_sources`
- `skill_keys`
- `mode`

位置：

- `page/models/contracts.py:168-185`

其中最关键的是：

```text
session_id
marker
template_id
prompt_template_id
datasources
knowledge_sources
skill_keys
mode
```

这些字段会影响整个生成路径，不是简单的附加参数。

例如原项目中：

- 指定 `prompt_template_id` 会进入 Prompt Template 分支；
- 指定 `skill_keys` 会强制执行 Skill；
- 指定 `knowledge_sources` 会加载知识库；
- 指定 `mode=chat` 可能不进入页面生成；
- 已存在 `session_id` 和 `marker` 时会继续已有会话或已有页面；
- 已存在页面时会进行增量修改，而不是重新生成。

建议先让 `sinan` 的 API 请求模型字段和原项目完全一致，再逐个实现字段语义。字段先加上但没有行为是不够的，必须配套测试每个分支。

### 4. 缺少认证和身份上下文

当前接口允许调用方在 body 中直接传：

```json
{
  "prompt": "...",
  "user_id": "someone"
}
```

这只是业务参数，不是认证。

原项目在生成路由中使用：

```python
auth: AuthResult = Depends(login_required)
```

位置：

- `page/api/routes/generate.py:67-78`

并且还处理：

- 登录状态；
- UUAP；
- UGate Token；
- 用户 token 缓存；
- Skill 调用时的用户身份；
- 鉴权失败统一响应。

当前 `sinan` 没有：

- `AuthResult`；
- `login_required`；
- 用户上下文；
- UGate Token；
- 鉴权异常；
- 权限控制；
- 资源归属校验。

这属于必须优先对齐的行为，因为它影响数据安全和所有后续接口。

## 五、任务生命周期没有对齐

### 1. 当前使用进程内后台任务

当前逻辑：

```python
session = await session_store.create(...)
asyncio.create_task(
    generation_runner.start(session.session_id, req.attachments)
)
```

位置：

- `sinan/api/routes/generate.py:35-43`

问题是：

- 进程重启，任务消失；
- worker 崩溃，任务消失；
- 多 worker 之间互相看不到任务；
- 无法判断任务是否被其他 worker 执行；
- 无法自动重试；
- 无法处理僵尸任务；
- 没有 lease；
- 没有 heartbeat；
- 没有 attempt 记录；
- 请求返回成功后，后台任务可能无法启动。

### 2. 原项目使用 Durable Job

原项目有独立的：

```text
generation_job
```

字段包括：

```text
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

位置：

- `page/models/tables.py:68-88`

执行方式是：

```text
创建 job
  → supervisor 定期扫描 pending/expired job
  → 抢占 lease
  → 执行任务
  → heartbeat
  → 成功/失败/取消
  → 释放或续期 lease
```

### 3. 当前已有数据库表，但核心任务表缺失

当前 `GenSession` 可以记录状态，但它并不等于原项目的 `GenerationJob`。

当前 `GenSession`：

- 偏向业务会话；
- 没有 lease；
- 没有 attempt；
- 没有 request_payload；
- 没有 job_id；
- 没有 worker owner；
- 没有恢复信息。

原项目将：

```text
GenerationSession
GenerationJob
GenerationArtifact
Page
PageVersion
```

拆成了不同职责。

建议：

1. 保留 `GenSession` 作为兼容层；
2. 新增 `GenerationJob`；
3. 将 `asyncio.create_task` 替换为 job 创建；
4. 实现单进程 supervisor；
5. 实现 lease 和 heartbeat；
6. 实现服务启动时恢复未完成任务；
7. 再考虑多 worker 和 Redis 锁。

不要一开始就做复杂分布式调度，先做到“单进程重启后任务可恢复”。

## 六、SSE 事件系统没有对齐

### 1. 当前是一次性内存队列

当前实现是：

```python
dict[session_id, asyncio.Queue]
```

位置：

- `sinan/services/generation_event_bus.py:31-64`

它只能保证：

- 当前进程内；
- 当前队列仍存在；
- 某个订阅者能消费到事件。

它不能保证：

- 断线重连；
- 事件历史回放；
- 多个客户端同时订阅；
- 多实例之间共享；
- 事件 ID；
- 断点续传；
- 服务重启后的事件可见。

当前代码的注释也已经明确说明，客户端断开后的 queue 清理还没有处理。

### 2. 原项目使用 Redis 事件回放

原项目生成 SSE 的关键逻辑：

```python
last_id = cursor or "0"

for message_id, event in await generation_event_bus.replay(session_id, last_id):
    ...

async for message_id, event in generation_event_bus.subscribe(session_id, last_id):
    ...
```

位置：

- `page/api/routes/generate.py:108-125`

这说明原项目具备：

- event id；
- cursor；
- 历史事件回放；
- 断线重连；
- Redis Stream 或类似机制；
- 事件终止类型；
- 多订阅者；
- 事件持久化。

### 3. 事件类型也没有完全对齐

当前项目已有：

- `step`
- `gate_passed`
- `code_generated`
- `code_snapshot`
- `code_delta`
- `code_stream_end`
- `verify_start`
- `fix_start`
- `verify_result`
- `fix_applied`
- `completed`
- `error`
- `chat`

原项目还涉及：

- `session_init`
- `skill_running`
- `skill_selected`
- `skill_result`
- `skill_link_required`
- `knowledge_source`
- `skill_keys`
- `awaiting_confirmation`
- runtime 工具调用事件；
- Opencode 事件；
- 用户确认事件；
- 取消事件；
- 页面产物事件；
- 代码快照事件；
- 错误恢复事件。

建议先冻结一份 SSE 事件协议：

```text
事件名
事件 ID
事件发生时机
data 字段
是否持久化
是否终止连接
是否允许重放
```

然后再实现 Redis 版本的 EventBus。

## 七、生成运行时没有对齐

### 1. 当前只有一条 LangGraph 路径

当前主链路是：

```text
LangGraph
  → analyze
  → design
  → code
  → verify
  → fix
```

### 2. 原项目至少有三种运行模式

原项目生成路由中已经明确出现：

```python
CodegenEngine
ClaudeCodeRuntime
RuntimeToolRegistry
PromptRouter
opencode_client
```

位置：

- `page/api/routes/generate.py:21-34`

主要路径是：

#### 路径 A：传统 Native/LangGraph

```text
Prompt
  → intent classifier
  → analyst
  → designer
  → coder
  → verifier
  → fixer
```

#### 路径 B：Claude Code Runtime

```text
Prompt
  → PromptRouter
  → ClaudeCodeRuntime
  → Tool Registry
  → Skill
  → runtime events
  → 页面代码
```

#### 路径 C：Opencode

```text
Prompt
  → Opencode Client
  → 流式事件
  → code/chat
  → 页面产物
```

并且还有：

```text
full opencode mode
hybrid codegen mode
native mode
```

对应：

- `page/api/routes/generate.py:88-96`

当前 `sinan` 没有：

- intent 分类；
- chat 分支；
- 修改已有页面分支；
- Claude Code Runtime；
- Opencode；
- Tool Registry；
- runtime event adapter；
- hybrid 模式；
- fallback 行为。

建议运行时对齐顺序：

1. 先把原项目传统 LangGraph 路径完整对齐；
2. 再对齐 chat / modify / template 路由；
3. 再实现 Runtime 抽象；
4. 再接入 Claude Code Runtime；
5. 最后接入 Opencode 和 hybrid/fallback。

不要一开始就同时实现三套运行时，否则很难判断问题来自哪里。

## 八、Agent State 差异很大

当前 `sinan` 的状态较简单：

```python
class PageGenState(TypedDict):
    prompt: str
    requirements: str
    design: str
    html: str
    verified: bool
    verify_message: str
    iteration: int
    max_iterations: int
    gate_decision: str
    attachments: list
    session_id: str
    marker: str
    user_id: str
```

位置：

- `sinan/agents/state.py:5-55`

原项目状态包含：

```text
session_id
marker
user_id
user_input
attachments
intent
requirement_doc
analysis_output
design_doc
code
code_hash
features
verification_result
pipeline_state
gate_reports
contract_errors
fix_round
max_fix_rounds
fix_history
repair_strategy
messages
history_messages
conversation_summary
long_term_memory
status
user_confirmed
iteration_feedback
created_at
updated_at
template_id
template_code
datasources
internal_skills
external_knowledge
force_auto_confirm
```

位置：

- `page/agents/state.py:11-73`

缺少的字段对应不同业务能力：

| 缺少字段 | 影响 |
|---|---|
| `intent` | 无法区分 chat/create/modify/template/data_query |
| `code_hash` | 无法判断页面版本变化 |
| `pipeline_state` | 无法表达正式流水线状态 |
| `gate_reports` | 无法完整审计质量门禁 |
| `contract_errors` | 无法追踪具体契约失败 |
| `fix_history` | 无法展示修复过程 |
| `messages` | 无法恢复对话 |
| `user_confirmed` | 无法实现确认节点 |
| `iteration_feedback` | 无法支持多轮修改 |
| `template_code` | 无法执行模板生成 |
| `datasources` | 无法接入真实数据 |
| `internal_skills` | 无法执行 Skill |
| `external_knowledge` | 无法注入知识库 |

## 九、数据模型差异

### 1. 当前模型更像基础版

当前核心表：

```text
gen_session
gen_session_step
page_version
```

其中页面内容直接存放在：

```text
html_content
source_code
```

位置：

- `sinan/models/tables.py:64-82`

### 2. 原项目模型更加拆分

原项目至少包括：

```text
generation_session
generation_artifact
generation_job
page
page_version
skill_definition
page_template
sys_user
buddy_profile
```

位置：

- `page/models/tables.py:25` 起；
- `page/models/tables.py:51` 起；
- `page/models/tables.py:68` 起；
- `page/models/tables.py:90` 起；
- `page/models/tables.py:113` 起；
- `page/models/tables.py:134` 起；
- `page/models/tables.py:153` 起。

### 3. 当前缺少 Page 主表

原项目把“页面”和“页面版本”分开：

```text
Page
  ├── current_version
  ├── published_version
  ├── published_to
  ├── quality_score
  ├── cover_url
  ├── tags
  └── status

PageVersion
  ├── bos_path
  ├── entry_file
  ├── file_list
  ├── content_hash
  ├── code_size
  ├── file_count
  ├── security_scan
  ├── harness_score
  └── repair_rounds
```

当前 `PageVersion` 同时承担了部分页面实体职责，后续会导致：

- 页面元数据和版本数据混在一起；
- 无法独立发布页面；
- 无法表达 current/published 版本；
- 无法管理多个文件；
- 无法表达产物 hash；
- 无法实现托管和安全扫描。

### 4. 当前没有 Artifact 概念

原项目的 `generation_artifact` 用来保存：

- 分析结果；
- 设计结果；
- 验证结果；
- 代码快照；
- 附件；
- Skill 输出；
- 中间产物；
- BOS 地址；
- artifact metadata。

当前 `gen_session_step` 只能存步骤 JSON，和 Artifact 不完全等价。

建议数据模型对齐顺序：

1. `GenerationSession`
2. `GenerationJob`
3. `GenerationArtifact`
4. `Page`
5. `PageVersion`
6. `Attachment`
7. `SkillDefinition`
8. `PageTemplate`
9. 用户和 Buddy 相关模型

其中前五项是生成主链路必须的，后面可以按功能逐步增加。

## 十、存储层差异

### 当前项目

当前页面内容直接放在数据库中：

```text
html_content
source_code
```

附件则主要通过本地文件和 JSON 保存。

### 原项目

原项目使用：

```text
MySQL
  → 会话、任务、页面元数据、事件关联信息

Redis
  → SSE 事件、缓存、运行时状态、token

BOS
  → 页面源码、附件、模板、Skill 包、页面产物
```

页面版本中主要存储：

```text
bos_path
entry_file
file_list
content_hash
code_size
file_count
security_scan
scan_result
harness_score
repair_rounds
```

这意味着原项目页面不一定是一个 HTML 字符串，而可能是一个完整的多文件产物：

```text
index.html
assets/
scripts/
styles/
components/
```

当前只有：

```text
一个 html 字符串
```

这是后续对齐中的关键架构差异。

## 十一、验证和 Harness 差异

### 当前验证能力

当前主要是：

- Contract 校验；
- HTML 最小结构检查；
- 浏览器基础验证；
- ECharts 检测；
- Gate 决策；
- fix 循环。

当前 Code Contract 主要检查：

```python
<!doctype
<html
<body
```

位置：

- `sinan/models/contracts.py:39-53`

这只能验证“是不是一个基本 HTML”，还不能说明它符合用户需求。

### 原项目验证器更完整

原项目包含：

```text
requirement validator
template validator
data validator
syntax validator
render validator
security validator
a11y validator
```

验证结果包含：

```text
issue_id
severity
category
description
location
suggestion
```

位置：

- `page/models/contracts.py:110-119`

质量分数按照 P0/P1/P2 问题计算：

```python
P0 → -0.30
P1 → -0.10
P2 → -0.02
```

位置：

- `page/models/contracts.py:122-134`

当前项目的验证结果主要是：

```text
verified: bool
verify_message: str
```

建议验证器从浅到深分成五层：

1. HTML 结构；
2. JS/浏览器运行；
3. 用户需求覆盖；
4. 数据绑定正确性；
5. 安全、无障碍、模板一致性。

每一层都输出结构化 `ValidationIssue`，而不是只返回一句文本。

## 十二、当前代码中值得特别注意的对齐风险

### 1. `PipelineStateMachine` 可能尚未真正接入

当前 `sinan/harness/state_machine.py` 定义了状态转移规则，但实际运行主要依赖 `LangGraph` 条件边。

这意味着：

```text
定义了状态机
```

不等于：

```text
运行时真的由状态机控制
```

需要确认：

- 所有状态是否都从状态机产生；
- LangGraph 是否绕过了状态机；
- 状态机转移和 Graph 转移是否可能不一致；
- 用户确认、取消、恢复是否能通过同一个状态机处理。

### 2. `SinanError` 没有形成统一异常协议

当前虽然定义了：

```python
class SinanError:
    message
    code
```

但 `sinan/api/app.py` 没有像原项目那样注册全局异常处理器。

原项目：

- `page/api/app.py:148-155`

因此当前项目可能出现：

- 业务异常直接变成 500；
- 错误格式不统一；
- SSE 错误和普通 HTTP 错误格式不同；
- 鉴权错误无法统一处理。

### 3. SSE 队列有潜在内存泄漏和事件丢失

当前事件总线的清理依赖收到 sentinel：

```python
if item is _SENTINEL:
    self._queues.pop(session_id, None)
```

但以下情况可能无法清理：

- SSE 客户端提前断开；
- runner 异常退出，没有执行 `publish_done`；
- 服务进程异常终止；
- 同一 session 多个订阅者；
- 客户端晚于任务完成才连接。

这也是为什么原项目需要 Redis replay。

### 4. `GenerateRequest` 使用可变默认值风格

当前：

```python
attachments: list[dict] = []
```

建议和原项目保持一致，改为：

```python
attachments: list[dict] = Field(default_factory=list)
```

这属于低优先级，但在重构学习过程中应尽早养成一致的模型写法。

## 十三、推荐的逐步对齐方案

不要按“原项目有哪些文件，就复制哪些文件”的方式推进。更适合学习目标的是：每一阶段对齐一个完整的外部行为闭环。

### Phase 0：建立对齐基线

目标：先知道什么叫“对齐”。

建立以下文件：

```text
docs/compatibility/
├── api-matrix.md
├── state-matrix.md
├── event-matrix.md
├── storage-matrix.md
├── runtime-matrix.md
└── behavior-cases.md
```

每个行为写成：

```text
场景：
输入：
原项目行为：
sinan 当前行为：
差异：
目标行为：
验证方式：
```

至少先整理这些场景：

1. 创建新页面；
2. 创建页面失败；
3. 页面生成中断线；
4. 页面生成完成后重新连接；
5. 取消生成；
6. 服务重启后任务恢复；
7. 生成聊天回复；
8. 修改已有页面；
9. 上传 Excel；
10. 上传图片；
11. 使用模板；
12. 使用 Skill；
13. 使用知识库；
14. 用户确认；
15. 用户反馈后二次生成；
16. 页面预览；
17. 页面发布；
18. 非法 ZIP 上传；
19. 未登录访问；
20. 不属于当前用户的 session 查询。

这一阶段不改业务代码，先建立学习地图。

### Phase 1：先对齐 API 表面

目标：让调用方式和原项目一致。

优先实现：

```text
/api/page/health
/api/page/ready
/api/page/generate
/api/page/session/...
/api/page/preview/...
/api/page/upload
/api/page/pages/...
```

重点工作：

1. API 路径改为原项目路径；
2. 请求字段对齐；
3. 响应字段对齐；
4. HTTP 状态码对齐；
5. 错误格式对齐；
6. SSE 的入口方式对齐；
7. OpenAPI 文档对齐。

此阶段可以暂时让新接口内部仍调用旧的 `sinan` 服务，但外部协议必须先一致。

验证方式：

为两个项目分别写黑盒测试：

```python
async def test_generate_request_shape():
    ...

async def test_health_response_shape():
    ...

async def test_invalid_request_error_shape():
    ...
```

不要先比较内部函数，而是先比较 HTTP 行为。

### Phase 2：对齐认证和用户上下文

目标：让所有资源都和用户绑定。

实现：

```text
AuthResult
login_required
request user context
trace_id
user_id resolution
UGate token extraction
```

顺序建议：

1. 先实现开发环境假的 Auth；
2. 再对齐原项目 header/cookie 读取方式；
3. 再实现鉴权失败响应；
4. 再给 session、page、artifact 加用户权限检查；
5. 最后接 UGate Token。

开发阶段可以有：

```text
SINAN_AUTH_MODE=mock
```

但不能一直默认允许 anonymous。

### Phase 3：把 Session 和 Job 分开

目标：实现可靠任务生命周期。

新增：

```text
GenerationSession
GenerationJob
```

建议状态：

```text
pending
running
awaiting_confirmation
completed
completed_with_warnings
failed
cancelled
```

新增字段：

```text
job_id
request_payload
lease_owner
lease_until
heartbeat_at
attempts
max_attempts
started_at
finished_at
```

执行器改为：

```text
POST
  → 创建 Session
  → 创建 Job
  → 返回/订阅

Supervisor
  → 获取待执行 Job
  → 抢 lease
  → 执行
  → heartbeat
  → 更新状态
```

先实现单进程版：

```text
一个 supervisor + MySQL
```

确认重启可恢复后，再接 Redis。

验证场景：

- runner 执行中杀掉进程；
- 重新启动服务；
- 任务是否重新执行；
- 同一 job 是否被重复执行；
- 超过最大尝试次数后是否失败；
- cancel 后是否还能继续生成。

### Phase 4：对齐 SSE 事件协议

目标：让事件成为稳定的公共协议。

先定义统一事件结构：

```json
{
  "id": "事件ID",
  "event": "code_delta",
  "session_id": "...",
  "marker": "...",
  "timestamp": "...",
  "data": {}
}
```

事件至少包含：

```text
session_init
step
gate_passed
code_delta
code_snapshot
verify_start
verify_result
fix_start
fix_applied
awaiting_confirmation
completed
error
cancelled
```

然后实现：

1. 事件 ID；
2. cursor；
3. 事件 replay；
4. 断线重连；
5. 多个订阅者；
6. 终止事件；
7. Redis Stream 或等价存储。

这一阶段完成后，才算真正对齐原项目的流式交互。

### Phase 5：对齐传统 LangGraph 行为

目标：把原项目基础生成链路完整复现。

先只处理：

```text
create page
```

对齐：

- 原项目的 intent；
- requirement 文档格式；
- analysis 输出字段；
- design 输出字段；
- code 输出结构；
- verifier 评分；
- fixer 路由；
- Gate；
- checkpoint；
- 每一步的事件；
- 中间产物保存。

此阶段不要引入 Skill、Opencode 和 Claude Code。

重点是建立一条“传统路径 100% 可验证”的基线。

### Phase 6：对齐用户确认和多轮修改

目标：实现原项目真正的交互式生成。

正式支持：

```text
analysis completed
  → awaiting_confirmation
  → user confirms
  → generation continues
```

以及：

```text
已有页面
  → 用户提出修改
  → intent = modify
  → RouteDecision
  → design 或 generation 局部重新进入
  → 保留未修改模块
  → 生成新版本
```

需要实现：

- `SessionConfirmRequest`；
- 确认接口；
- 反馈接口；
- 迭代路由；
- 结构性修改；
- 局部修改；
- 会话消息；
- 版本递增；
- 旧版本保留。

这是从“单轮生成器”变成“页面创作平台”的关键一步。

### Phase 7：对齐数据、附件和产物模型

目标：从“一个 HTML 字符串”升级为“完整页面产物”。

先实现：

```text
Attachment
GenerationArtifact
Page
PageVersion
```

附件支持顺序：

1. Excel；
2. CSV；
3. 图片；
4. 原始文件保存；
5. 解析结果保存；
6. 生成上下文注入；
7. 附件与 session/page 关联。

页面产物支持：

```text
index.html
styles.css
app.js
assets/*
```

页面版本存：

```text
entry_file
file_list
content_hash
code_size
file_count
security_scan
scan_result
harness_score
repair_rounds
```

BOS 可以先用本地对象存储兼容层模拟：

```text
StorageBackend
  ├── LocalStorage
  └── BOSStorage
```

这样可以先学习原项目的存储抽象，而不必一开始依赖完整 BOS 环境。

### Phase 8：对齐 Skill、模板和知识库

目标：实现原项目的扩展能力。

#### 8.1 Template

先实现：

- 模板列表；
- 模板详情；
- `template_id`；
- HTML 模板加载；
- Prompt Template；
- 模板生成分支。

#### 8.2 Skill Registry

实现：

- SkillDefinition；
- Skill 列表；
- Skill 启停；
- Skill 安装；
- Skill 内容更新；
- Skill 包同步；
- Skill 运行事件；
- Skill 输出保存。

#### 8.3 知识库

实现：

- `knowledge_sources`；
- 文档链接校验；
- 文档抓取；
- 内容解析；
- 上下文注入；
- 需要用户补充链接时进入 `awaiting_confirmation`。

#### 8.4 真实业务 Skill

最后再接：

- 数据查询；
- GPU delivery；
- PL analysis；
- ku-doc；
- UGate Token。

不要在 Skill Registry 还没稳定时直接复制原项目中的所有 Skill。

### Phase 9：对齐 Claude Code / Opencode Runtime

目标：实现原项目的新生成路径。

建议先抽象统一接口：

```python
class GenerationRuntime(Protocol):
    async def run(self, state) -> AsyncIterator[RuntimeEvent]:
        ...
```

然后实现：

```text
NativeLangGraphRuntime
ClaudeCodeRuntime
OpencodeRuntime
HybridRuntime
```

统一转成：

```text
RuntimeEvent
  → SSEEvent
  → Artifact
  → Session status
```

对齐内容：

- chat 分支；
- tool call；
- code delta；
- code snapshot；
- runtime error；
- Opencode fallback；
- hybrid 模式；
- 已有页面编辑；
- 对话历史传递。

这样 `api/routes/generate.py` 不会继续膨胀成一个几百行的总控制器。

### Phase 10：对齐预览、托管和安全

最后实现：

- 页面预览；
- 版本预览；
- ZIP 上传；
- ZIP 路径穿越防护；
- 文件扩展名限制；
- HTML/JS 安全扫描；
- 页面外部托管；
- 发布状态；
- current/published version；
- 页面访问权限。

这部分不是生成主链路，但属于原项目的重要外部能力。

## 十四、建议的代码重构顺序

为了学习效果和控制复杂度，建议迁移顺序是：

```text
1. API contracts
2. Auth/context
3. Session/Job
4. EventBus/SSE
5. Native LangGraph
6. Confirmation/iteration
7. Artifact/Page/Version
8. Upload/storage
9. Template
10. Skill
11. Knowledge base
12. Claude Code runtime
13. Opencode
14. Hosting/security
15. Observability/admin
```

不要按照原项目目录顺序直接重写，因为原项目的目录顺序不等于功能依赖顺序。

## 十五、现在最应该立即做的三件事

### 第一件：冻结 API 对照表

优先比较：

```text
路径
HTTP 方法
请求参数
响应结构
状态码
异常
鉴权
SSE 事件
```

这是最容易客观验证的一层。

### 第二件：把 Job 从 Session 中拆出来

当前最大的架构缺口是：

```python
asyncio.create_task(...)
```

应该先替换成：

```text
创建 GenerationJob
→ supervisor 执行
→ heartbeat
→ 可恢复
```

在这个问题解决之前，后面的 SSE、页面版本、Runtime 对齐都会建立在不可靠的任务基础上。

### 第三件：建立黑盒兼容测试

不要只测试当前实现能不能生成页面，而要测试：

```text
给同样的输入
→ 原项目返回什么
→ sinan 返回什么
→ 差异在哪里
```

建议测试目录：

```text
tests/compatibility/
├── test_health.py
├── test_generate_api.py
├── test_sse_protocol.py
├── test_session_lifecycle.py
├── test_confirmation.py
├── test_modify_page.py
├── test_upload.py
├── test_preview.py
└── test_error_contract.py
```

“百分百一致”最终应该由这些测试定义，而不是由目录结构定义。

## 十六、最终判断

当前项目的完成度可以粗略理解为：

```text
基础页面生成链路：        已有较完整基础
传统 LangGraph 对齐：      约 40%
API 对齐：                 约 20%
任务生命周期对齐：         约 10%
SSE 对齐：                 约 20%
数据模型对齐：             约 25%
Harness 对齐：             约 30%
Skill/模板/知识库：        约 5%
Claude Code/Opencode：     约 0%~10%
发布/托管/安全：           约 5%
```

这不是说你的项目做得不好，而是原项目本身已经从“生成流程”演进成了“完整平台”。现在最适合的学习路径是：

```text
先做到 API 行为一致
  → 再做到任务可恢复
  → 再做到 SSE 可回放
  → 再做到传统生成链一致
  → 再做到用户确认和多轮修改
  → 再补数据、模板、Skill
  → 最后接入多运行时和发布系统
```

其中最重要的认知是：

> 不要把“文件和类名一致”当作重构完成；应该把“同样输入下的外部行为、状态变化、事件顺序、产物结果和异常结果一致”作为完成标准。
