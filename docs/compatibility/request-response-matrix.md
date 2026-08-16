# 请求与响应兼容性矩阵

## 生成与流式请求

| 场景 | 参考项目 | 当前 sinan | 差异/验证 |
|---|---|---|---|
| 新建生成 | `POST /api/page/generate`，认证，SSE 200 | `POST /api/v1/generate`，无认证，JSON `{session_id,status}` | 路径、认证、协议均不同；需 TestClient/真实 SSE 验证 |
| 请求字段 | `prompt(min=2)`、`session_id`、`marker`、附件、模板、数据源、知识库、Skill、mode | `prompt`、`user_id`、`attachments` | 当前缺少复用和运行时选择字段 |
| 空 prompt | Pydantic 422（空值/长度不满足） | 目前可进入创建流程 | 需锁定 HTTP 码和错误 JSON |
| 过长 prompt | 需以参考配置/模型实际限制验证 | 未声明上限 | 记录实际边界，不凭注释猜测 |
| 生成失败 | SSE 已建立后发送 `error` 事件，通常 HTTP 仍为 200 | SSE 中发送 `error`，Session 置 `failed` | 事件 payload、终止事件和重连行为不同 |
| 页面预览 | `/api/page/preview/{marker}` HTML | `/api/v1/page/{marker}` HTML | 路径不同；当前版本和预览 URL 由 `generation_runner.py:139` 写入 |
| 资源不存在 | 参考预览通常 404；Session 部分接口 HTTP 200、JSON 内容码 404 | 以当前路由实现为准 | 必须用矩阵测试锁定接口级行为 |

## 统一记录格式

每个黑盒用例应记录：请求方法和 URL、认证 Cookie、请求体、HTTP 状态码、响应头、完整响应体/SSE 原文、数据库快照、事件顺序、重连位置和结论。

## 错误协议待验证项

参考项目的 `AuthenticationError` 默认码为 401（`page/core/exceptions.py:14`），但未认证访问、资源越权、Pydantic 422、业务 400 必须分别测试，不能只按异常类推断。
