# 行为基线用例清单

状态含义：`部分` 表示当前有局部代码但不能声称兼容；`缺失` 表示没有对应公开能力；`待测` 表示必须连接参考服务才能锁定实际响应。

| ID | 场景 | 参考 | sinan 当前 | 验证重点 |
|---:|---|---|---|---|
| 1 | 新建页面 | 有 | 部分（Step 7） | SSE/Session/Page 持久化 + `gate_reports`/`quality_score` 真值 |
| 2 | Prompt 为空 | 有，422 | 部分 | 空值与最短长度 |
| 3 | Prompt 过长 | 有约束待测 | 无声明 | 实际边界 |
| 4 | 普通聊天输入 | 有，mode/chat | 缺失 | 路由与事件（参考在 API 层用 `classify_intent` 拦截，属 Step 8） |
| 5 | 页面生成失败 | 有，SSE error | 部分 | error payload/状态；失败原因现取 `verification_result.issues` 前 5 条 `description` |
| 6 | 生成中客户端断线 | 有 | 部分（Step 5） | 事件已落 Redis List，重连带 `Last-Event-ID`/`cursor` 从断点补发；待黑盒验证不丢不重 |
| 7 | 完成后重新连接 | 有 | 部分（Step 5） | 终止事件后 key TTL 120s，晚到客户端仍可收到 `completed`；TTL 过期后的行为待确认 |
| 8 | 取消生成 | 有 abort | 部分（Step 4） | Redis `cancel_registry` 支持运行中节点边界打断+cancelled 事件；打断粒度/事件顺序待黑盒验证 |
| 9 | 服务重启恢复 | 有 Job Supervisor | 部分（Step 4） | lease/retry/supervisor 已具备，待黑盒验证 |
| 10 | 复用已有 Session | 有 | 部分（Step 4） | `create_or_get_job` 按 session 复用活动 Job，session_id 语义待验证 |
| 11 | 修改已有页面 | 有 iterate | 方案就绪（Step 8，待实施） | `POST /session/{id}/iterate` + `iteration_router.classify_iteration` + `direct_editor`；runner `_run_iterate` 产出新 PageVersion，旧版本不可变。待黑盒验证：结构性/局部/文本替换三分支路由与版本递进 |
| 12 | 用户确认 | 有 confirm | 部分→方案就绪（Step 8） | 挂起已具备（Step 7）；`POST /session/{id}/confirm` confirmed=true 置 active 并重跑图（iteration_feedback 非空使 analyst 不再挂起）。待验证：确认后 SSE 续流与最终版本 |
| 13 | 用户拒绝 | 有 confirm(false) | 方案就绪（Step 8，待实施） | `_run_confirm` 拒绝分支：保留 paused、发 `awaiting_confirmation`(rejected=true, feedback)。待验证 payload 与参考差异 |
| 14 | 反馈后二次生成 | 有 | 方案就绪（Step 8，待实施） | `create_action_job(action=iterate)` 建新 Job → supervisor 执行 → 新版本。待验证 Job/版本链路 |
| 15 | 上传 Excel | 有 | 部分 | 元数据、内容和权限 |
| 16 | 上传 CSV | 有 | 部分 | 解析和存储 |
| 17 | 上传图片 | 有 | 缺失/待测 | MIME、对象存储 |
| 18 | 非法 ZIP | 有 | 缺失/待测 | 安全校验和 400 |
| 19 | 页面模板 | 有 | 缺失 | template_id；`TemplateValidator` 已就位（Step 7），缺 `template_code` 注入（Step 11） |
| 20 | Prompt Template | 有 | 缺失 | 模板列表/生成 |
| 21 | Skill | 有 | 部分（Step 12） | 显式 `skill_keys` 强制选择、关键词路由、`skill_running`/`skill_result` 事件、失败不阻断。**差异**：sinan 从本地 `sinan/skills/` 目录装包（参考从 BOS zip）；sinan 打开了关键词路由（参考的 auto 路由被硬关，`codegen_engine.py:508`）|
| 22 | 知识库链接 | 有 | 部分（Step 12） | `knowledge_sources` 本地文件解析 → `knowledge_source` 事件 → `knowledge` Artifact → `external_knowledge` 注入 analyst/coder。**差异**：HTTP 抓取默认关闭（`knowledge_allow_http=False`），参考默认走 httpx + ku 二进制 |
| 23 | 页面预览 | 有 | 部分 | 路径、404、HTML |
| 24 | 页面版本预览 | 有 | 部分 | version URL 和权限 |
| 25 | 页面发布 | 有 host | 缺失 | publish/hosting 状态 |
| 26 | 未认证访问 | 有认证边界 | 无认证层 | 401/公开资源 |
| 27 | 访问他人 Session | 有 403 边界 | 缺失 | owner 校验 |
| 28 | 访问他人 Page | 有认证 API | 缺失 | Page owner 校验 |

每条用例执行时按实施计划中的统一格式记录：场景、输入、原项目响应/数据库/事件、sinan 响应/数据库/事件、差异、目标行为、验证方式。

## Step 7 新增基线用例（需与参考同输入对照）

| ID | 场景 | 参考 | sinan 当前 | 验证重点 |
|---:|---|---|---|---|
| 29 | Router 意图分类 | 有，4 类 create/modify/template/data_query | 部分 | `intent`/`confidence`/`extracted_info` 字段与解析失败兜底值（`{create, 0.5, {page_type: dashboard}}`） |
| 30 | 验证问题清单 | 5 个 validator（requirement/template/data/syntax/render） | 部分（缺 Vision 视觉检查） | `issue_id`/`severity`/`category` 逐条对照；sinan 侧 issue 会更少 |
| 31 | 质量分计算 | P0=0.30 / P1=0.10 / P2=0.02 累加，下限 0.0 | 是 | 同一 issues 输入下 `quality_score` 必须完全一致 |
| 32 | 修复轮次与策略 | 1/2/3 → conservative/moderate/aggressive | 是 | `fix_history` 的 `round`/`strategy`/`issues_before` |
| 33 | 契约违规记录 | 记录不阻断；ANALYSIS 与 VALIDATION 稳定失败 | 是 | `contract_errors` 的 `step` 与 `errors` 结构 |
| 34 | 门禁报告 | 6 个门，报告 6 字段 | 部分 | `gen_session.gate_reports` 的 `gate`/`step`/`passed`/`score`；sinan 多 `decision`/`issues`/`timestamp` |
| 35 | 修满轮次仍不通过 | complete_with_warnings 出口，`passed` 仍 False | 是 | Job/Session 是否都落 failed、`verify_result` payload 与错误文案 |
| 36 | 低置信度挂起 | analyst confidence < 0.3 → awaiting_confirmation | 部分 | Session=paused、Job=waiting、事件 payload；参考 `pipeline_state` 写 `analysis`，sinan 写 `user_confirm` |

## Step 12 新增基线用例

标注「已本地实测」的项是用一次性自检脚本（已删除）直接调服务层/路由层验证过的；
其余仍需与参考同输入对照。

| ID | 场景 | 参考 | sinan 当前 | 验证重点 |
|---:|---|---|---|---|
| 37 | 显式 skill_keys 强制选择 | 有（`forced_skill_keys`） | 是（已本地实测） | `skill_keys=["static-sales"]` 时 `_source=explicit` 且不走路由；库里没有的 key 保留占位记录（`_source=explicit_missing`）并以 `ok=false, error="handler not found"` 结束——参考同样保留占位 |
| 38 | Prompt 路由命中 Skill | 代码在但被硬关 | sinan 打开关键词路由（已本地实测） | "用模拟数据做个收入看板" → `mock-metrics`（命中词 `模拟数据`）；"做一个区域销售额看板" → `static-sales`；"做个时间页面" → 不选。`skill_running.explicit=false`。**已知差异**：参考此场景不会选任何 Skill |
| 39 | Skill 执行失败 | 记录 + `skill_result.success=false`，不挂起 | 同（`tool_registry.execute` 全异常收敛） | handler 缺失 / 子进程超时（`skill_timeout_seconds`）/ 非零退出 / stdout 非 JSON 四种情况都应 `success=false` 且流水线继续；`skill_context.failed` 有记录 |
| 40 | 缺链接挂起 | `skill_link_required` → 会话挂起 | 是（已本地实测分支） | 事件顺序必须是 `skill_link_required` → `awaiting_confirmation{link_required:true}`；Session=paused、Job=waiting；`_after_skill` 使图在 skill 节点后 END |
| 41 | 补链接后续跑 | 用户补链接 → 继续 | 是 | `POST /session/{id}/confirm` 带 `link` 或 `knowledge_sources` → runner `_build_state` 合并 → 新 confirm Job 重跑 skill 节点真正加载知识。**sinan 增量**：`user_confirmed=True` 时跳过链接门，避免"确认但仍不给链接"导致无限挂起 |
| 42 | 知识源非法 | SSRF / 不可达时降级 | 是（已本地实测） | `../../etc/passwd` → `路径越界`；`missing.md` → `文件不存在`；`http://127.0.0.1/x` → `HTTP 知识源已禁用`；三种都 `success=false` 且不阻断，合法源照常合并 |
| 43 | Skill 输出落 Artifact | 有 | 是 | `generation_artifact` 应有 `skill_{skill_key}` 与 `knowledge` 两类记录，>=64KB 卸载到 LocalStorage（Step 9 机制） |
| 44 | 数据源五类型 | api/static/database/file/mock | 4 类可用 + database 显式 unsupported（已本地实测） | 每条结果都带 `data_schema`/`sample_data`/`error_policy`；`db:` 返回"不支持执行"而非静默；`file:` 越界/缺失有明确 error |
| 45 | Skill 跨用户隔离 | 有认证边界 | 结构上无越权面，但**未验证** | 子进程只透传 `PATH/LANG/LC_ALL/PYTHONPATH/HOME`，不注入任何凭证；`knowledge_context._resolve_local` 限定 `knowledge_dir` 前缀；`skill_dir` 拒绝含 `/`、`\`、前导 `.` 的 key。真实多用户隔离依赖 Step 3（已评估跳过） |
| 46 | 本地包安装与状态 | 远端 zip 安装 | 是（已本地实测） | 启动 `sync_enabled_skills()` 把 `sinan/skills/` 两个包 upsert 为 `enabled`；人工 `disabled` 的包不会被重启同步重新启用；缺 `handler.py` 的包落 `failed` 且不被 `list_available()` 选中 |
