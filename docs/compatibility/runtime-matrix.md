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
| 配置 | `RUN_ENV` 选择 config | `settings.py` 已分组，Step 7 新增 `auto_confirm_threshold=0.3`/`max_fix_rounds=3`/`quality_threshold=0.8`/`render_validation_enabled=False`/`render_validation_timeout=20`；Step 12 新增 `skills_dir`/`skill_timeout_seconds=60`/`skill_output_limit`/`skill_sse_preview_limit=2000`/`skill_route_by_llm=False`/`knowledge_*`/`datasource_*` | 键值与参考 `dev.config` 一致，仅 `render_validation_enabled` 参考为 true；`RUN_ENV` 多环境 config 文件机制仍缺失。Step 12 的路径类配置（`skills_dir`/`knowledge_dir`）相对路径按**项目根**解析，与参考 `_PROJECT_ROOT` 同思路，不受启动工作目录影响 |
| 附件 | Upload/Storage/BOS | 本地解析 JSON | 仅局部兼容 |
| LLM 调用方式 | `llm.ainvoke(messages, system=..., role=...)`，analyst/designer 非流式 | `LLMClient.chat/astream`，analyst/designer/coder 流式（Step 5 固化） | 未对齐：sinan 多 `analysis_delta`/`design_delta` 事件，且流式与非流式的输出内容可能有细微差异 |
| 默认生成图节点数 | 6 节点 | **7 节点（Step 12）**：`router → skill → analyst → designer → coder → verifier → fixer`，`skill` 不套 `wrap_node` | 未对齐（sinan 增量）：参考把 Skill 预处理放在 runtime 层（`claude_code/codegen_engine.preprocess_skill`）而非图节点，因为参考的 native graph 不跑 Skill。sinan 只有 native graph，所以做成图节点；Step 13 接 Runtime 抽象后需重新评估是否下移 |
| Skill 工具注册表 | `claude_code/skill_executor.py` + `codegen_engine` 选择逻辑，包来自 BOS zip，子进程注入 UGATE_TOKEN / PL_API_* | `runtime/tool_registry.py`（选择/过滤/执行/归一化）+ `services/skill_registry.py`（落库）+ `services/skill_package.py`（本地包解析） | 机制对齐（显式优先 → 路由、子进程 + `asyncio.wait_for` 超时、输出归一化与截断）；包来源与凭证注入有意不对齐 |
| Skill 路由 | 显式 `skill_keys` 优先；LLM/规则/领域关键词路由代码在但被硬关（`codegen_engine.py:508`） | 显式优先；关键词路由默认开启，LLM 路由由 `skill_route_by_llm`（默认 False）控制 | 有意不对齐：不开路由则「Prompt 能路由到匹配 Skill」这条验收标准无法验证。Step 15 对照时可把两侧都置为"只认显式" |
| 知识库摄取 | httpx + ku 二进制，SSRF 校验，1MB / 50000 字符上限 | `services/knowledge_context.py` + `services/document_parser.py`，本地文件优先，HTTP 默认关闭（`knowledge_allow_http=False`），开启后保留 SSRF 校验与 1MB 上限 | 流程对齐（校验 → 读取 → 解析 → 限长 → 清洗 → Artifact → 注入 state）；传输层有意不对齐 |
| 数据源 | api / static / database / file / mock，语义散落在 opencode_context / skill_executor | `contracts.DataSourceConfig` + `data_service.resolve_datasources()`，五要素显式化（data_schema / sample_data / fetch / timeout / error_policy） | 4 类可用；`database` 显式返回 unsupported（不接真实库），属有意差异 |

需要用相同 prompt、相同 runtime 参数和相同附件分别采集：runtime 选择、步骤事件、最终 PageVersion、错误和资源消耗。
