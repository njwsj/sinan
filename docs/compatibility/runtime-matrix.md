# Runtime 兼容性矩阵

| 维度 | 参考项目 | 当前 sinan | 结论 |
|---|---|---|---|
| 默认生成图 | Native LangGraph/Harness 分支 | `build_graph(llm)`，`astream_events` | 需按事件和状态黑盒对齐 |
| Runtime 选择 | `mode`、配置及 Claude Code/Opencode/Hybrid 分支 | GenerateRequest 没有 mode，仅固定 graph | 缺失 |
| 请求上下文 | UUAP 用户、UGate token、配置环境 | 已加 trace_id 中间件 + contextvars（`sinan/api/context.py`），user 仍来自请求，认证待 Step 3 | trace_id 已对齐；认证语义待 Step 3 |
| 任务执行 | DB Job Supervisor、租约、恢复 | `asyncio.create_task` | 进程生命周期不可靠 |
| 事件通道 | Redis durable bus | 单进程队列 | 无断线回放 |
| 配置 | `RUN_ENV` 选择 config | `settings.py` 已分组并新增 `database_url`/`redis_url`/`bos_*`/`auth_mode`/`opencode_*`/`job_*` 键 | 键已补齐；`RUN_ENV` 多环境 config 文件机制仍缺失（参考用 dev/sandbox/online.config），待验证 |
| 附件 | Upload/Storage/BOS | 本地解析 JSON | 仅局部兼容 |

需要用相同 prompt、相同 runtime 参数和相同附件分别采集：runtime 选择、步骤事件、最终 PageVersion、错误和资源消耗。
