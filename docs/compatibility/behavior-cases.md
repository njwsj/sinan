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
| 11 | 修改已有页面 | 有 iterate | 缺失 | 版本和上下文（state 已有 `iteration_feedback`/`history_messages` 占位，行为属 Step 8） |
| 12 | 用户确认 | 有 confirm | 部分（Step 7） | 低置信度已能挂起：session=paused、pipeline_state=user_confirm、job=waiting、发 `awaiting_confirmation`；确认接口属 Step 8 |
| 13 | 用户拒绝 | 有 confirm(false) | 缺失 | rejected/反馈（Step 8） |
| 14 | 反馈后二次生成 | 有 | 缺失 | 新 Job/版本 |
| 15 | 上传 Excel | 有 | 部分 | 元数据、内容和权限 |
| 16 | 上传 CSV | 有 | 部分 | 解析和存储 |
| 17 | 上传图片 | 有 | 缺失/待测 | MIME、对象存储 |
| 18 | 非法 ZIP | 有 | 缺失/待测 | 安全校验和 400 |
| 19 | 页面模板 | 有 | 缺失 | template_id；`TemplateValidator` 已就位（Step 7），缺 `template_code` 注入（Step 11） |
| 20 | Prompt Template | 有 | 缺失 | 模板列表/生成 |
| 21 | Skill | 有 | 缺失 | skill_keys/admin API |
| 22 | 知识库链接 | 有 | 缺失 | knowledge_sources |
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
