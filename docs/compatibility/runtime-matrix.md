# Runtime 兼容性矩阵

| 维度 | 参考项目 | 当前 sinan | 结论 |
|---|---|---|---|
| 默认生成图 | Native LangGraph/Harness：6 节点（router/analyst/designer/coder/verifier/fixer）+ 2 条件边，5 个业务节点由 `wrap_node` 包 harness | 同构（Step 7）：`build_graph(llm)` 6 节点 + `harness/orchestrator.wrap_node`，`astream_events` 驱动 | 结构已对齐；四个旧 `gate_*` 节点已删除，门禁不再决定路由 |
| Harness | 节点后统一跑 契约校验 → 质量门 → checkpoint(MySQL+BOS+Redis) | 节点后跑 契约校验 → 质量门 → session/artifact 落库 | 前两段已对齐；checkpoint 层未对齐（无 `harness_checkpoint` 表，靠 `MemorySaver`） |
| 校验器 | 5 个：requirement/template/data/syntax/render（render 含 Playwright + Vision LLM 28 项视觉检查） | 同 5 个（Step 7），render 只做 JS 错误采集，无 Vision | 未对齐项：缺视觉检查；且 `render_validation_enabled` 默认 False，Step 15 对照前必须开启并装 playwright |
| Runtime 选择 | `mode`、配置及 Claude Code/Opencode/Hybrid 分支 | GenerateRequest 有 `mode` 字段但未使用，仅固定 native graph | 缺失（Step 13/14） |
| chat 分支 | API 层用 `classify_intent` 拦截，不进图（`page/api/routes/generate.py:180`） | 无 | 缺失（Step 8） |
| 请求上下文 | UUAP 用户、UGate token、配置环境 | trace_id 已对齐；认证部分 **暂不实现（已评估跳过）**：沿用固定用户 `anonymous`，`request_user_var` 仍可记录，UGate token 无接入需求 | trace_id 已对齐；认证/token 非 agent 核心，已跳过，将来需要登录时再做 Step 3 |
| 任务执行 | DB Job Supervisor、租约、恢复 | `generation_job` + 租约 + supervisor（Step 4） | 已对齐结构；`waiting` 态自 Step 7 起启用 |
| 事件通道 | Redis durable bus | Redis List + INCR seq（Step 5） | 已对齐 |
| 配置 | `RUN_ENV` 选择 config | `settings.py` 已分组，Step 7 新增 `auto_confirm_threshold=0.3`/`max_fix_rounds=3`/`quality_threshold=0.8`/`render_validation_enabled=False`/`render_validation_timeout=20` | 键值与参考 `dev.config` 一致，仅 `render_validation_enabled` 参考为 true；`RUN_ENV` 多环境 config 文件机制仍缺失 |
| 附件 | Upload/Storage/BOS | 本地解析 JSON | 仅局部兼容 |
| LLM 调用方式 | `llm.ainvoke(messages, system=..., role=...)`，analyst/designer 非流式 | `LLMClient.chat/astream`，analyst/designer/coder 流式（Step 5 固化） | 未对齐：sinan 多 `analysis_delta`/`design_delta` 事件，且流式与非流式的输出内容可能有细微差异 |

需要用相同 prompt、相同 runtime 参数和相同附件分别采集：runtime 选择、步骤事件、最终 PageVersion、错误和资源消耗。
