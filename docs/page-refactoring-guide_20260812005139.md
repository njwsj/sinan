# Page 项目重构指南：从零到一构建 AI 页面生成系统

> 基于 `page` 代码库 + 技术方案文档，采用**垂直切片（Vertical Slice）**策略，每个阶段交付可端到端运行的完整功能。

---

## 目录

- [一、项目全景认知](#一项目全景认知)
- [二、重构路线总览（垂直切片）](#二重构路线总览垂直切片)
- [三、Phase 0：项目骨架搭建](#三phase-0项目骨架搭建)
- [四、Phase 1：最小可运行原型 — "Hello HTML"](#四phase-1最小可运行原型--hello-html)
- [五、Phase 2：接入 LLM — 让 AI 生成页面](#五phase-2接入-llm--让-ai-生成页面)
- [六、Phase 3：LangGraph 多 Agent 编排](#六phase-3langgraph-多-agent-编排)
- [七、Phase 4：Harness 工程化 — 质量护栏](#七phase-4harness-工程化--质量护栏)
- [八、Phase 5：数据服务与托管发布](#八phase-5数据服务与托管发布)
- [九、Phase 6：迭代增强与生产化](#九phase-6迭代增强与生产化)
- [十、技术栈与依赖清单](#十技术栈与依赖清单)
- [十一、原项目模块映射表](#十一原项目模块映射表)
- [十二、关键设计决策对比](#十二关键设计决策对比)

---

## 一、项目全景认知

### 1.1 这个项目是什么？

**Page** 是一个 AI 驱动的页面生成服务，核心能力是：用户用自然语言描述需求 → 系统自动生成可预览、可数据绑定的动态页面。

核心流程：
```
用户输入需求 + 附件(Excel/HTML/图片)
    ↓
Analyzer（需求分析）→ Designer（页面设计）→ Coder（代码生成）
    ↓
Verifier（Harness验证）→ Fixer（自动修复，最多3轮）
    ↓
Host（托管发布）→ 返回预览链接
```

### 1.2 原项目目录结构

```
page/
├── agents/                    # AI Agent 编排（核心）
│   ├── analyst.py            # 需求分析 Agent
│   ├── coder.py              # 代码生成 Agent
│   ├── designer.py           # 页面设计 Agent
│   ├── direct_editor.py      # 零LLM直接DOM编辑
│   ├── fixer.py              # 自动修复 Agent
│   ├── graph.py              # LangGraph 状态图主入口
│   ├── graph_provider.py     # Graph 提供者（工厂/选择）
│   ├── intent_classifier.py  # 意图分类（新建 vs 编辑）
│   ├── llm.py                # LLM 调用统一封装
│   ├── router.py             # 路由（条件边）
│   ├── state.py              # GenerationState 状态定义
│   └── verifier.py           # 验证 Agent
├── api/                       # FastAPI Web 层
│   ├── app.py                # FastAPI 应用入口
│   ├── cancel_registry.py    # 任务取消注册
│   ├── context.py            # 请求上下文
│   ├── deps.py               # 依赖注入
│   ├── opencode_stream.py    # OpenCode 流式接口
│   ├── runtime_stream.py     # 运行时 SSE 流
│   ├── sse.py                # SSE 推送工具
│   └── routes/               # API 路由
├── buddy/                     # Buddy 辅助模块
├── claude_code/               # Claude Code 集成模块
├── config/                    # 多环境配置
│   ├── dev.config            # 开发环境
│   ├── online.config         # 线上环境
│   ├── sandbox.config        # 沙箱环境
│   └── settings.py           # 配置加载器
├── core/                      # 基础工具
│   ├── exceptions.py         # 自定义异常
│   ├── http.py               # HTTP 工具
│   └── time.py               # 时间工具
├── harness/                   # Harness 工程（质量护栏）
│   ├── checkpoint.py         # Checkpoint 持久化
│   ├── contracts.py          # 契约校验（Pydantic Schema）
│   ├── gates.py              # 门禁节点
│   ├── iteration_router.py   # 迭代路由（精确回退）
│   ├── orchestrator.py       # 管道编排器
│   ├── repair.py             # 修复策略
│   ├── state_machine.py      # 状态机
│   └── validators/           # 验证器集合
├── models/                    # 数据模型
│   ├── contracts.py          # Pydantic 契约模型
│   ├── database.py           # SQLAlchemy 数据库连接
│   ├── enums.py              # 枚举
│   └── tables.py             # 数据库表定义
├── preview/                   # 预览服务
│   ├── service.py            # 预览逻辑
│   └── strategies.py         # 预览策略
├── services/                  # 业务服务层
│   ├── buddy_service.py      # Buddy 服务
│   ├── generation_event_bus.py  # 生成事件总线
│   ├── generation_job_store.py # 生成任务持久化
│   ├── generation_runner.py  # 生成运行器（调用 LangGraph）
│   ├── image_parser.py       # 图片解析
│   ├── memory.py             # 上下文记忆
│   ├── opencode.py           # OpenCode 集成
│   ├── opencode_context.py   # OpenCode 上下文
│   ├── prompt_template_generator.py  # Prompt 模板生成
│   ├── security.py           # 安全扫描
│   ├── session_store.py      # Session 存储
│   ├── skill_package.py      # 技能包
│   ├── skill_registry.py     # 技能注册
│   ├── storage.py            # 文件存储
│   ├── ugate_token_store.py  # UGate Token 存储
│   ├── uuap.py               # UUAP 认证
│   ├── web_auth.py           # Web 认证
│   └── web_session.py        # Web Session
├── tests/                     # 测试
├── __init__.py
├── __main__.py
├── cmdline.py                # CLI 入口
├── Dockerfile                # 生产 Docker
└── Dockerfile_sandbox        # 沙箱 Docker
```

### 1.3 技术栈一览

| 组件 | 选型 | 用途 |
|------|------|------|
| Web 框架 | FastAPI + uvicorn | REST API + SSE 推送 |
| Agent 编排 | LangGraph + langgraph-checkpoint-mysql | 状态图、条件分支、Checkpoint |
| LLM | GLM-5.1（原项目自建）→ **你用智谱 API** | 代码生成、需求分析、设计 |
| 数据库 | MySQL（SQLAlchemy + aiomysql） | Session、任务、页面版本 |
| 缓存 | Redis | Session 状态、设计稿缓存 |
| 数据校验 | Pydantic v2 + pydantic-settings | 契约模型、配置管理 |
| 浏览器验证 | Playwright | Harness 阶段页面渲染验证 |
| Excel 解析 | openpyxl + pandas | 数据源解析 |
| 模板引擎 | Jinja2 | Prompt 模板渲染 |
| HTTP 客户端 | httpx | 异步 HTTP 调用 |
| 重试 | tenacity | API 调用重试 |
| HTML 解析 | beautifulsoup4 | 验证阶段 DOM 检查 |
| 容器化 | Docker | 部署 |

### 1.4 三份技术方案核心要点

**初始方案（V1）**：定义了 Analyzer→Designer→Coder→Verifier→Fixer→Host 的核心流程，LangGraph 状态图，Session Journal，SSE 流式反馈。

**迭代方案（V2）**：增加了 Harness Engineering — 每步后插入门禁节点（gate_xxx），契约校验（JSON Schema），Checkpoint 持久化，审计 API。

**Harness 工程设计（V3）**：详细设计了 Pipeline Orchestrator、State Machine、Contract Validator、Gate Engine、Checkpoint Store、Event Bus 六大组件，七步管道（Ingestion→Analysis→Design→Generation→Validation→Preview→Iteration）。

---

## 二、重构路线总览（垂直切片）

核心理念：**每个 Phase 结束时，你都有一个能跑通、能看到结果的完整功能**，然后逐层加深。

```
Phase 0: 项目骨架搭建        → 能启动的空壳服务
Phase 1: 最小可运行原型      → "给我一个描述，还你一个 HTML 页面"（硬编码，无LLM）
Phase 2: 接入 LLM            → 智谱 API 驱动代码生成（单步，无编排）
Phase 3: LangGraph 多 Agent  → Analyzer→Designer→Coder→Verifier→Fixer 全流程
Phase 4: Harness 工程化      → 契约校验 + 门禁 + Checkpoint + 审计
Phase 5: 数据服务与托管发布   → Excel 数据源 + 页面托管 + 版本管理
Phase 6: 迭代增强与生产化    → 安全扫描 + 迭代编辑 + 多数据源 + 部署
```

### 你的思路 vs 调整建议

| 你的思路 | 调整建议 | 原因 |
|---------|---------|------|
| 先搭后端框架（DB+Redis） | ✅ 正确，Phase 0 做 | 基础设施先行没问题 |
| 然后补充 LLM | ⚠️ 建议先做 Phase 1 硬编码版 | 先跑通骨架再接 LLM，避免"没有 LLM 就没法测" |
| 再补充 LangGraph | ✅ 正确，Phase 3 做 | LangGraph 需要先有单步 LLM 调用基础 |
| 再补充 Harness | ✅ 正确，Phase 4 做 | Harness 是质量层，需要先有流程才能加护栏 |
| BOS 如果必须再买 | ⚠️ Phase 5 才需要，前期用本地文件存储 | 先跑通核心流程再接外部存储 |

---

## 三、Phase 0：项目骨架搭建

**目标**：搭建项目骨架，能 `python -m page` 启动一个空壳 FastAPI 服务，数据库表和 Redis 连接就绪。

**预计工时**：1-2 天

### 3.1 创建项目结构

```
page-gen/                      # 你的新项目
├── pyproject.toml             # 项目配置（hatchling 构建）
├── requirements.txt           # 依赖锁定
├── README.md
├── .python-version            # 3.12
├── Dockerfile
├── page_gen/                   # 主包
│   ├── __init__.py
│   ├── __main__.py            # python -m page_gen
│   ├── cmdline.py             # CLI 入口
│   ├── api/                    # Web 层
│   │   ├── __init__.py
│   │   ├── app.py             # FastAPI 应用
│   │   ├── deps.py            # 依赖注入
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── generate.py    # 生成相关路由
│   │       └── health.py      # 健康检查
│   ├── config/                 # 配置
│   │   ├── __init__.py
│   │   ├── settings.py        # Pydantic Settings
│   │   └── dev.config         # 开发配置
│   ├── core/                   # 基础设施
│   │   ├── __init__.py
│   │   ├── exceptions.py      # 自定义异常
│   │   └── logging.py         # 日志配置
│   ├── models/                 # 数据模型
│   │   ├── __init__.py
│   │   ├── database.py        # SQLAlchemy 引擎
│   │   ├── tables.py          # 表定义
│   │   └── enums.py           # 枚举
│   └── services/              # 业务服务（Phase 0 只放占位）
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_health.py
└── docker-compose.yml         # MySQL + Redis 本地开发
```

### 3.2 关键依赖（requirements.txt）

```txt
# Web 框架
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sse-starlette>=2.0.0

# 数据校验
pydantic>=2.9.0
pydantic-settings>=2.5.0

# 数据库
sqlalchemy[asyncio]>=2.0.35
aiomysql>=0.2.0
pymysql>=1.1.0

# 缓存
redis>=5.2.0

# HTTP
httpx>=0.27.0
python-multipart>=0.0.12

# 工具
orjson>=3.10.0
tenacity>=9.0.0
jinja2>=3.1.0
pyyaml>=6.0

# 测试
pytest
pytest-asyncio
httpx
mock
```

> **注意**：Phase 0 先不装 langgraph、playwright 等，后面按需添加。

### 3.3 数据库表设计（MySQL）

根据原项目 `models/tables.py` 和技术方案，设计核心表：

```sql
-- 生成会话表
CREATE TABLE gen_session (
    id VARCHAR(64) PRIMARY KEY COMMENT '会话ID',
    user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
    prompt TEXT NOT NULL COMMENT '用户需求描述',
    status ENUM('pending','running','completed','failed','awaiting_input') DEFAULT 'pending',
    current_step VARCHAR(32) DEFAULT NULL COMMENT '当前步骤',
    iteration INT DEFAULT 0 COMMENT '修复迭代次数',
    max_iterations INT DEFAULT 3,
    marker VARCHAR(128) DEFAULT NULL COMMENT '页面标识',
    version INT DEFAULT NULL COMMENT '版本号',
    preview_url TEXT DEFAULT NULL,
    total_tokens INT DEFAULT 0,
    total_duration_ms INT DEFAULT 0,
    error_message TEXT DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_status (user_id, status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 会话步骤明细表（Session Journal）
CREATE TABLE gen_session_step (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL,
    step VARCHAR(32) NOT NULL COMMENT 'receive/analyze/design/code/verify/fix/host',
    direction VARCHAR(16) DEFAULT NULL COMMENT 'input/output',
    input_data JSON DEFAULT NULL COMMENT '步骤输入',
    output_data JSON DEFAULT NULL COMMENT '步骤输出',
    contract_result JSON DEFAULT NULL COMMENT '契约校验结果',
    gate_decision VARCHAR(32) DEFAULT NULL COMMENT '门禁决策',
    token_usage INT DEFAULT 0,
    duration_ms INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id, step),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 页面版本表
CREATE TABLE page_version (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    marker VARCHAR(128) NOT NULL COMMENT '页面标识',
    version INT NOT NULL COMMENT '版本号',
    html_content LONGTEXT COMMENT 'HTML内容',
    source_code LONGTEXT COMMENT '源代码',
    status ENUM('draft','published','archived') DEFAULT 'draft',
    owner VARCHAR(64) DEFAULT NULL COMMENT '所有者',
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_marker_version (marker, version),
    INDEX idx_marker (marker)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Checkpoint 表（LangGraph Checkpoint）
-- 注意：langgraph-checkpoint-mysql 会自动创建自己的表，这里只定义业务表
```

### 3.4 Redis 用途规划

```python
# Phase 0 只需要连接，Phase 1+ 逐步使用
# 用途：
# 1. Session 状态缓存（key: session:{id} → 状态 JSON）
# 2. 设计稿缓存（key: design:{session_id} → 设计稿 JSON）
# 3. 任务队列（key: task:queue → list）
# 4. SSE 事件通道（key: sse:{session_id} → pub/sub）
```

### 3.5 配置系统

```python
# page_gen/config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # 应用
    app_name: str = "page-gen"
    debug: bool = True

    # 数据库
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "page_gen"

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    # LLM（Phase 2 接入）
    llm_api_key: str = ""           # 智谱 API Key
    llm_model: str = "glm-4"        # 智谱模型
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # 页面托管（Phase 5）
    storage_type: str = "local"     # local | bos
    storage_local_path: str = "./output/pages"

    class Config:
        env_file = ".env"
```

### 3.6 docker-compose.yml（本地开发）

```yaml
version: "3.8"
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root123
      MYSQL_DATABASE: page_gen
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  mysql_data:
```

### 3.7 验收标准（Phase 0）

- [ ] `docker-compose up -d` 启动 MySQL + Redis
- [ ] `pip install -e .` 安装项目
- [ ] `python -m page_gen` 启动 FastAPI 服务
- [ ] `GET /health` 返回 `{"status": "ok"}`
- [ ] 数据库表自动创建
- [ ] Redis 连接正常

---

## 四、Phase 1：最小可运行原型 — "Hello HTML"

**目标**：用户发送一段文字描述，系统返回一个硬编码的 HTML 页面。**不接 LLM**，只跑通骨架。

**预计工时**：2-3 天

### 1.1 本阶段做什么

1. **API 层**：`POST /api/v1/generate` 接收用户 prompt，返回 session_id
2. **SSE 推送**：`GET /api/v1/generate/{session_id}/stream` 推送步骤进度
3. **生成运行器**：硬编码一个"生成器"，根据 prompt 返回固定 HTML 模板
4. **Session 存储**：MySQL 持久化 + Redis 缓存
5. **预览**：`GET /api/v1/page/{marker}` 返回 HTML 内容

### 1.2 核心代码骨架

```python
# page_gen/api/routes/generate.py
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/v1/generate")

@router.post("")
async def create_generation(prompt: str = Body(...)):
    """创建生成任务"""
    session = await session_store.create(prompt=prompt)
    # 异步启动生成流程
    await generation_runner.start(session.id)
    return {"session_id": session.id, "status": "running"}

@router.get("/{session_id}/stream")
async def stream_generation(session_id: str):
    """SSE 推送生成进度"""
    async def event_generator():
        async for event in generation_event_bus.subscribe(session_id):
            yield {"event": event.type, "data": event.json()}
    return EventSourceResponse(event_generator())
```

```python
# page_gen/services/generation_runner.py（Phase 1 硬编码版）
class GenerationRunner:
    async def start(self, session_id: str):
        session = await session_store.get(session_id)
        # 步骤 1: 接收
        await self._emit(session_id, "receive", "正在接收需求...")
        # 步骤 2: "分析"（硬编码）
        await self._emit(session_id, "analyze", "正在分析需求...")
        await asyncio.sleep(0.5)
        # 步骤 3: "生成"（硬编码 HTML）
        await self._emit(session_id, "code", "正在生成页面...")
        html = self._template_html(session.prompt)
        # 步骤 4: "验证"（硬编码通过）
        await self._emit(session_id, "verify", "验证通过")
        # 步骤 5: 托管
        marker = f"page_{session_id[:8]}"
        version = 1
        await page_store.save(marker, version, html)
        await self._emit(session_id, "host", f"已托管: /page/{marker}")
        # 完成
        await session_store.update(session_id, status="completed",
                                    marker=marker, version=version)
```

### 1.3 验收标准

- [ ] `POST /api/v1/generate` with `{"prompt": "做一个数据看板"}` 返回 session_id
- [ ] SSE 流推送 5 个步骤事件
- [ ] `GET /api/v1/page/{marker}` 返回 HTML 页面
- [ ] 数据库中有完整的 session 和 step 记录
- [ ] **端到端跑通，能看到一个 HTML 页面**

---

## 五、Phase 2：接入 LLM — 让 AI 生成页面

**目标**：用智谱 API 替换硬编码生成器，实现"描述→HTML"的单步 LLM 生成。

**预计工时**：2-3 天

### 2.1 LLM 封装

```python
# page_gen/agents/llm.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMClient:
    def __init__(self, api_key: str, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
```

### 2.2 单步 Coder Agent

```python
# page_gen/agents/coder.py（Phase 2 简化版）
class CoderAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def generate(self, prompt: str) -> str:
        """根据用户描述直接生成 HTML"""
        system_prompt = """你是一个前端页面生成专家。
根据用户需求生成完整的 HTML 页面（内联 CSS 和 JS）。
要求：
1. 使用 ECharts 做图表
2. 响应式布局
3. 现代化 UI 风格
4. 返回纯 HTML，不要 markdown 代码块
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        html = await self.llm.chat(messages, temperature=0.3)
        # 去除可能的 markdown 包裹
        if html.startswith("```html"):
            html = html[7:]
        if html.endswith("```"):
            html = html[:-3]
        return html.strip()
```

### 2.3 改造 GenerationRunner

```python
# Phase 2: 替换硬编码为真实 LLM 调用
class GenerationRunner:
    def __init__(self, llm: LLMClient, coder: CoderAgent):
        self.llm = llm
        self.coder = coder

    async def start(self, session_id: str):
        session = await session_store.get(session_id)
        await self._emit(session_id, "receive", "正在接收需求...")

        # 真实 LLM 生成
        await self._emit(session_id, "code", "AI 正在生成页面...")
        html = await self.coder.generate(session.prompt)

        await self._emit(session_id, "verify", "验证通过")
        marker = f"page_{session_id[:8]}"
        version = 1
        await page_store.save(marker, version, html)
        await self._emit(session_id, "host", f"已托管: /page/{marker}")
        await session_store.update(session_id, status="completed",
                                    marker=marker, version=version)
```

### 2.4 验收标准

- [ ] 输入"做一个 GPU 使用率看板"，AI 返回真实 HTML 页面
- [ ] SSE 流推送生成进度
- [ ] 页面可在浏览器中预览
- [ ] LLM 调用失败时有错误处理和重试
- [ ] **端到端跑通：自然语言 → AI 生成 → 预览页面**

---

## 六、Phase 3：LangGraph 多 Agent 编排

**目标**：将单步 LLM 调用升级为 Analyzer→Designer→Coder→Verifier→Fixer 多 Agent 流程，使用 LangGraph 状态图编排。

**预计工时**：5-7 天

### 3.1 安装 LangGraph

```bash
pip install langgraph>=0.2.0 langchain-core>=0.3.0 langgraph-checkpoint-mysql>=3.0.0
```

### 3.2 状态定义（参考原项目 state.py）

```python
# page_gen/agents/state.py
from typing import TypedDict, List, Optional

class GenerationState(TypedDict):
    # 用户输入
    session_id: str
    user_id: str
    prompt: str
    attachments: List[dict]

    # 步骤产出
    requirement_doc: Optional[dict]      # Analyzer 输出
    design_spec: Optional[dict]          # Designer 输出
    html_code: Optional[str]             # Coder 输出
    verify_report: Optional[dict]        # Verifier 输出
    fix_history: List[dict]              # 修复历史

    # 流程控制
    current_step: str
    iteration: int
    max_iterations: int                  # 默认 3
    status: str                          # running|completed|failed|awaiting_input

    # 托管结果
    marker: Optional[str]
    version: Optional[int]
    preview_url: Optional[str]

    # 统计
    total_tokens: int
    total_duration_ms: int
```

### 3.3 构建 LangGraph 状态图（参考原项目 graph.py）

```python
# page_gen/agents/graph.py
from langgraph.graph import StateGraph, END

def build_generation_graph(llm: LLMClient):
    analyzer = AnalyzerAgent(llm)
    designer = DesignerAgent(llm)
    coder = CoderAgent(llm)
    verifier = VerifierAgent()
    fixer = FixerAgent(llm)

    graph = StateGraph(GenerationState)

    # 添加节点
    graph.add_node("analyze", analyzer.run)
    graph.add_node("design", designer.run)
    graph.add_node("code", coder.run)
    graph.add_node("verify", verifier.run)
    graph.add_node("fix", fixer.run)
    graph.add_node("host", host_page)

    # 定义边
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "design")
    graph.add_edge("design", "code")
    graph.add_edge("code", "verify")

    # 条件边：验证结果决定下一步
    def route_verify(state: GenerationState) -> str:
        if state["verify_report"]["passed"]:
            return "host"
        if state["iteration"] < state["max_iterations"]:
            return "fix"
        return END  # 超过最大次数，标记失败

    graph.add_conditional_edges("verify", route_verify, {
        "host": "host",
        "fix": "fix",
        END: END,
    })
    graph.add_edge("fix", "code")    # 修复后重新生成代码
    graph.add_edge("host", END)

    return graph.compile()
```

### 3.4 各 Agent 实现

```python
# page_gen/agents/analyst.py
class AnalyzerAgent:
    """需求分析：解析用户描述，生成结构化需求文档"""
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        prompt = f"""分析以下页面需求，输出结构化 JSON：
{state['prompt']}

输出格式：
{{
  "appName": "应用名称",
  "appDescription": "描述",
  "pageType": "dashboard|form|list|detail|landing",
  "targetUser": "目标用户",
  "dataSource": {{"type": "static", "description": "数据说明"}},
  "pageStructure": {{
    "layout": "布局描述",
    "regions": [{{"id": "xxx", "type": "header|kpi_group|chart_group|data_table", "components": [...]}}]
  }},
  "styleSpec": {{"theme": "light", "primaryColor": "#4f6ef7", "chartLibrary": "ECharts"}},
  "acceptanceCriteria": ["验收标准1", "验收标准2"]
}}"""
        result = await self.llm.chat([
            {"role": "system", "content": "你是需求分析专家，输出 JSON。"},
            {"role": "user", "content": prompt}
        ], temperature=0.2)
        return {"requirement_doc": json.loads(result), "current_step": "analyze"}
```

```python
# page_gen/agents/designer.py
class DesignerAgent:
    """页面设计：基于需求文档生成布局设计稿"""
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        prompt = f"""基于以下需求文档，设计页面布局：
{json.dumps(state['requirement_doc'], ensure_ascii=False)}

输出设计稿 JSON，包含：layout（grid 布局）、regions（每个区域的组件树和 props）"""
        result = await self.llm.chat([
            {"role": "system", "content": "你是页面设计专家，输出 JSON。"},
            {"role": "user", "content": prompt}
        ], temperature=0.3)
        return {"design_spec": json.loads(result), "current_step": "design"}
```

```python
# page_gen/agents/coder.py（Phase 3 增强版）
class CoderAgent:
    """代码生成：基于设计稿生成完整 HTML"""
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        # 如果有修复历史，带上修复建议
        fix_context = ""
        if state.get("fix_history"):
            last_fix = state["fix_history"][-1]
            fix_context = f"\n\n上一轮验证失败原因：{last_fix['issues']}\n请修复这些问题。"

        prompt = f"""基于以下设计稿生成完整 HTML 页面：
{json.dumps(state['design_spec'], ensure_ascii=False)}

要求：
1. 内联 CSS 和 JS
2. 使用 ECharts 做图表
3. 响应式布局
4. 现代化 UI
5. 返回纯 HTML{fix_context}"""
        result = await self.llm.chat([
            {"role": "system", "content": "你是前端代码生成专家，只返回 HTML 代码。"},
            {"role": "user", "content": prompt}
        ], temperature=0.2)
        html = result.strip()
        if html.startswith("```html"):
            html = html[7:]
        if html.endswith("```"):
            html = html[:-3]
        return {"html_code": html.strip(), "current_step": "code"}
```

```python
# page_gen/agents/verifier.py（Phase 3 基础版）
class VerifierAgent:
    """验证：检查 HTML 基础质量"""
    def run(self, state: GenerationState) -> dict:
        html = state.get("html_code", "")
        issues = []

        # 基础检查
        if not html or len(html) < 100:
            issues.append("HTML 内容过短")
        if "<html" not in html.lower():
            issues.append("缺少 <html> 标签")
        if "<body" not in html.lower():
            issues.append("缺少 <body> 标签")
        if "<script" not in html.lower() and "<style" not in html.lower():
            issues.append("缺少 script 或 style 标签")

        passed = len(issues) == 0
        return {
            "verify_report": {"passed": passed, "issues": issues},
            "current_step": "verify"
        }
```

```python
# page_gen/agents/fixer.py
class FixerAgent:
    """自动修复：根据验证报告生成修复方案"""
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: GenerationState) -> dict:
        issues = state.get("verify_report", {}).get("issues", [])
        fix_entry = {"iteration": state["iteration"] + 1, "issues": issues}
        return {
            "fix_history": state.get("fix_history", []) + [fix_entry],
            "iteration": state["iteration"] + 1,
            "current_step": "fix"
        }
```

### 3.5 改造 GenerationRunner

```python
# page_gen/services/generation_runner.py（Phase 3 版）
from langgraph.checkpoint.memory import MemorySaver

class GenerationRunner:
    def __init__(self, llm: LLMClient):
        self.graph = build_generation_graph(llm)
        self.checkpointer = MemorySaver()  # Phase 4 换成 MySQL

    async def start(self, session_id: str):
        session = await session_store.get(session_id)
        initial_state = GenerationState(
            session_id=session_id,
            user_id=session.user_id,
            prompt=session.prompt,
            attachments=[],
            requirement_doc=None,
            design_spec=None,
            html_code=None,
            verify_report=None,
            fix_history=[],
            current_step="analyze",
            iteration=0,
            max_iterations=3,
            status="running",
            marker=None,
            version=None,
            preview_url=None,
            total_tokens=0,
            total_duration_ms=0,
        )

        # SSE 事件回调
        config = {"configurable": {"thread_id": session_id}}

        # 执行图
        final_state = await self.graph.ainvoke(initial_state, config=config)

        # 托管
        if final_state.get("html_code"):
            marker = f"page_{session_id[:8]}"
            version = 1
            await page_store.save(marker, version, final_state["html_code"])
            await session_store.update(session_id, status="completed",
                                        marker=marker, version=version)
```

### 3.6 验收标准

- [ ] 输入"做一个销售数据看板"，Analyzer 输出结构化需求 JSON
- [ ] Designer 输出布局设计稿
- [ ] Coder 输出完整 HTML
- [ ] Verifier 检查通过/失败
- [ ] 失败时 Fixer 触发修复，最多 3 轮
- [ ] 每一步的输入输出都记录到 `gen_session_step` 表
- [ ] SSE 推送每一步进度
- [ ] **端到端跑通：需求→分析→设计→生成→验证→修复→托管**

---

## 七、Phase 4：Harness 工程化 — 质量护栏

**目标**：为每个步骤添加契约校验、门禁节点、Checkpoint 持久化，实现 Harness 工程。

**预计工时**：5-7 天

### 4.1 核心概念

Harness 工程的三个核心组件：

1. **Contract Validator（契约校验器）**：每步输入/输出用 Pydantic Schema 校验
2. **Gate Engine（门禁引擎）**：每步后判断 proceed/retry/block
3. **Checkpoint Store（检查点存储）**：每步完成后保存快照，支持回滚

### 4.2 契约模型（参考原项目 models/contracts.py + harness/contracts.py）

```python
# page_gen/models/contracts.py
from pydantic import BaseModel, Field
from typing import List, Optional

class DataSourceConfig(BaseModel):
    type: str  # "api" | "static" | "excel"
    endpoint: Optional[str] = None
    description: Optional[str] = None

class NormalizedRequirement(BaseModel):
    """Step 1 输出契约"""
    appName: str = Field(..., min_length=1)
    appDescription: str = Field(..., min_length=1)
    pageType: str  # dashboard|form|list|detail|landing
    targetUser: str = ""
    dataSource: DataSourceConfig
    pageStructure: dict  # 布局结构
    styleSpec: dict      # 样式规格
    acceptanceCriteria: List[str] = Field(..., min_length=1)

class DesignSpec(BaseModel):
    """Step 2 输出契约"""
    layout: dict         # 布局
    regions: List[dict]  # 区域列表
    componentTree: dict  # 组件树

class CodeOutput(BaseModel):
    """Step 3 输出契约"""
    html: str = Field(..., min_length=100)
    hasScript: bool
    hasStyle: bool

class VerifyReport(BaseModel):
    """Step 4 输出契约"""
    passed: bool
    issues: List[str] = []
    score: float = Field(0.0, ge=0.0, le=1.0)
```

### 4.3 状态机（参考原项目 harness/state_machine.py）

```python
# page_gen/harness/state_machine.py
from enum import Enum
from typing import Optional

class PipelineState(Enum):
    INIT = "init"
    ANALYSIS = "analysis"
    DESIGN = "design"
    GENERATION = "generation"
    VALIDATION = "validation"
    FIX = "fix"
    HOST = "host"
    COMPLETED = "completed"
    FAILED = "failed"

TRANSITION_TABLE = {
    PipelineState.INIT: [PipelineState.ANALYSIS],
    PipelineState.ANALYSIS: [PipelineState.DESIGN, PipelineState.FAILED],
    PipelineState.DESIGN: [PipelineState.GENERATION, PipelineState.ANALYSIS],  # 可回退
    PipelineState.GENERATION: [PipelineState.VALIDATION],
    PipelineState.VALIDATION: [PipelineState.HOST, PipelineState.FIX, PipelineState.FAILED],
    PipelineState.FIX: [PipelineState.GENERATION],
    PipelineState.HOST: [PipelineState.COMPLETED, PipelineState.FAILED],
    PipelineState.COMPLETED: [],
    PipelineState.FAILED: [],
}

def can_transition(from_state: PipelineState, to_state: PipelineState) -> bool:
    return to_state in TRANSITION_TABLE.get(from_state, [])
```

### 4.4 门禁节点（参考原项目 harness/gates.py）

```python
# page_gen/harness/gates.py
from typing import Protocol

class GateResult:
    def __init__(self, decision: str, reason: str = "", issues: list = None):
        self.decision = decision  # "proceed" | "retry" | "block"
        self.reason = reason
        self.issues = issues or []

class GateEngine:
    """门禁引擎：每步后判断是否继续"""
    
    def evaluate(self, step: str, output: dict, state: dict) -> GateResult:
        method = getattr(self, f"_gate_{step}", None)
        if method:
            return method(output, state)
        return GateResult(decision="proceed")

    def _gate_analyze(self, output: dict, state: dict) -> GateResult:
        req = output.get("requirement_doc", {})
        if not req.get("appName"):
            return GateResult("retry", "appName 为空", ["appName missing"])
        if not req.get("pageStructure", {}).get("regions"):
            return GateResult("retry", "regions 为空", ["regions missing"])
        return GateResult("proceed")

    def _gate_design(self, output: dict, state: dict) -> GateResult:
        spec = output.get("design_spec", {})
        if not spec.get("layout"):
            return GateResult("retry", "layout 为空", ["layout missing"])
        if not spec.get("regions"):
            return GateResult("retry", "regions 为空", ["regions missing"])
        return GateResult("proceed")

    def _gate_code(self, output: dict, state: dict) -> GateResult:
        html = output.get("html_code", "")
        if not html or len(html) < 100:
            return GateResult("fix", "HTML 内容过短", ["html too short"])
        if "<html" not in html.lower():
            return GateResult("fix", "缺少 html 标签", ["missing html tag"])
        return GateResult("proceed")

    def _gate_verify(self, output: dict, state: dict) -> GateResult:
        report = output.get("verify_report", {})
        if report.get("passed"):
            return GateResult("proceed")
        if state.get("iteration", 0) < state.get("max_iterations", 3):
            return GateResult("retry", "验证未通过", report.get("issues", []))
        return GateResult("block", "超过最大修复次数")
```

### 4.5 Checkpoint 持久化（参考原项目 harness/checkpoint.py）

```python
# page_gen/harness/checkpoint.py
import json
from datetime import datetime

class CheckpointStore:
    """每步完成后保存状态快照到 MySQL"""
    
    async def save(self, session_id: str, step: str, version: int, state: dict):
        # 存入 gen_session_step 表
        await db.execute(
            "INSERT INTO gen_session_step (session_id, step, direction, output_data, created_at) "
            "VALUES (:sid, :step, 'checkpoint', :data, :ts)",
            values={
                "sid": session_id, "step": step,
                "data": json.dumps(state, ensure_ascii=False),
                "ts": datetime.now()
            }
        )

    async def load(self, session_id: str, step: str, version: int = None) -> dict:
        # 从 gen_session_step 表加载
        sql = "SELECT output_data FROM gen_session_step WHERE session_id=:sid AND step=:step"
        if version:
            sql += " AND version=:ver"
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = await db.fetch_one(sql, values={"sid": session_id, "step": step})
        return json.loads(row["output_data"]) if row else None

    async def rollback(self, session_id: str, step: str, version: int):
        """回滚到指定步骤的指定版本"""
        state = await self.load(session_id, step, version)
        if state:
            return state
        raise ValueError(f"Checkpoint not found: {step}@v{version}")
```

### 4.6 改造 LangGraph 图（加入门禁）

```python
# page_gen/agents/graph.py（Phase 4 版）
def build_generation_graph(llm: LLMClient):
    analyzer = AnalyzerAgent(llm)
    designer = DesignerAgent(llm)
    coder = CoderAgent(llm)
    verifier = VerifierAgent()
    fixer = FixerAgent(llm)
    gate_engine = GateEngine()
    checkpoint = CheckpointStore()

    async def gate_analyze(state):
        result = gate_engine.evaluate("analyze", state, state)
        return {"gate_decision": result.decision}

    async def gate_design(state):
        result = gate_engine.evaluate("design", state, state)
        return {"gate_decision": result.decision}

    async def gate_code(state):
        result = gate_engine.evaluate("code", state, state)
        return {"gate_decision": result.decision}

    async def gate_verify(state):
        result = gate_engine.evaluate("verify", state, state)
        return {"gate_decision": result.decision}

    graph = StateGraph(GenerationState)
    graph.add_node("analyze", analyzer.run)
    graph.add_node("gate_analyze", gate_analyze)
    graph.add_node("design", designer.run)
    graph.add_node("gate_design", gate_design)
    graph.add_node("code", coder.run)
    graph.add_node("gate_code", gate_code)
    graph.add_node("verify", verifier.run)
    graph.add_node("gate_verify", gate_verify)
    graph.add_node("fix", fixer.run)
    graph.add_node("host", host_page)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "gate_analyze")
    graph.add_conditional_edges("gate_analyze", lambda s: s.get("gate_decision", "proceed"), {
        "proceed": "design",
        "retry": "analyze",
    })
    graph.add_edge("design", "gate_design")
    graph.add_conditional_edges("gate_design", lambda s: s.get("gate_decision", "proceed"), {
        "proceed": "code",
        "retry": "design",
    })
    graph.add_edge("code", "gate_code")
    graph.add_conditional_edges("gate_code", lambda s: s.get("gate_decision", "proceed"), {
        "proceed": "verify",
        "fix": "fix",
    })
    graph.add_edge("verify", "gate_verify")
    graph.add_conditional_edges("gate_verify", lambda s: s.get("gate_decision", "proceed"), {
        "proceed": "host",
        "retry": "fix",
        "block": END,
    })
    graph.add_edge("fix", "code")
    graph.add_edge("host", END)

    # MySQL Checkpoint（Phase 4 用 langgraph-checkpoint-mysql）
    from langgraph.checkpoint.mysql import AsyncMySqlSaver
    checkpointer = AsyncMySqlSaver.from_conn_string(db_url)
    return graph.compile(checkpointer=checkpointer)
```

### 4.7 验证器增强（参考原项目 harness/validators/）

Phase 4 可以用 Playwright 做真实浏览器验证：

```python
# page_gen/harness/validators/browser_validator.py
from playwright.async_api import async_playwright

class BrowserValidator:
    """用 Playwright 做真实浏览器验证"""
    
    async def validate(self, html: str) -> dict:
        issues = []
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            try:
                await page.set_content(html)
                # 检查 JS 错误
                errors = await page.evaluate("() => window.__jsErrors || []")
                if errors:
                    issues.extend([f"JS Error: {e}" for e in errors])
                # 检查 ECharts 渲染
                charts = await page.query_selector_all("[_echarts_instance_]")
                if not charts and "echarts" in html.lower():
                    issues.append("ECharts 未正确初始化")
                # 检查空白区域
                body_text = await page.inner_text("body")
                if len(body_text.strip()) < 10:
                    issues.append("页面内容为空")
            finally:
                await browser.close()

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "chart_count": len(charts) if 'charts' in dir() else 0,
        }
```

### 4.8 审计 API

```python
# page_gen/api/routes/audit.py
@router.get("/{session_id}/audit")
async def get_audit(session_id: str):
    """获取会话审计轨迹"""
    steps = await db.fetch_all(
        "SELECT * FROM gen_session_step WHERE session_id=:sid ORDER BY created_at",
        values={"sid": session_id}
    )
    return {
        "sessionId": session_id,
        "totalSteps": len(steps),
        "auditTrail": [
            {
                "step": s["step"],
                "direction": s["direction"],
                "gateDecision": s["gate_decision"],
                "timestamp": s["created_at"].isoformat(),
            }
            for s in steps
        ]
    }
```

### 4.9 验收标准

- [ ] 每个 Agent 步骤后有契约校验
- [ ] 契约校验失败时自动 retry
- [ ] 验证失败时自动进入 fix 循环，最多 3 轮
- [ ] 每步状态保存到 MySQL Checkpoint
- [ ] `GET /api/v1/generate/{id}/audit` 返回审计轨迹
- [ ] Playwright 验证器检查 JS 错误和 ECharts 渲染
- [ ] **端到端跑通：带质量护栏的完整生成流程**

---

## 八、Phase 5：数据服务与托管发布

**目标**：支持 Excel 数据源接入、页面版本管理、预览服务。

**预计工时**：5-7 天

### 5.1 数据服务

```python
# page_gen/services/data_service.py
import openpyxl
import pandas as pd
from io import BytesIO

class DataService:
    """数据服务：支持 Excel 上传和模型化查询"""
    
    async def parse_excel(self, file_data: bytes) -> dict:
        """解析 Excel，返回字段 schema + 数据"""
        wb = openpyxl.load_workbook(BytesIO(file_data))
        sheet = wb.active
        df = pd.read_excel(BytesIO(file_data))
        
        columns = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            col_type = "text"
            if dtype in ("int64", "float64"):
                col_type = "number"
            elif dtype == "datetime64[ns]":
                col_type = "date"
            
            columns.append({
                "name": str(col),
                "displayName": str(col),
                "type": col_type,
                "role": "dimension" if col_type == "text" or col_type == "date" else "measure",
                "sampleValues": df[col].head(5).tolist(),
            })
        
        return {
            "sheets": [{
                "name": sheet.title,
                "columns": columns,
                "rowCount": len(df),
                "data": df.to_dict(orient="records"),
            }]
        }
```

### 5.2 页面托管服务

```python
# page_gen/services/page_store.py
import os
import json
from pathlib import Path

class PageStore:
    """页面版本管理 + 托管"""
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    async def save(self, marker: str, version: int, html: str, owner: str = ""):
        """保存页面版本"""
        # 存文件
        page_dir = self.storage_path / marker / str(version)
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(html, encoding="utf-8")
        
        # 存数据库
        await db.execute(
            "INSERT INTO page_version (marker, version, html_content, status, owner, created_by) "
            "VALUES (:marker, :version, :html, 'draft', :owner, :created_by)",
            values={"marker": marker, "version": version, "html": html,
                    "owner": owner, "created_by": owner}
        )

    async def get(self, marker: str, version: int = None) -> dict:
        """获取页面"""
        if version:
            row = await db.fetch_one(
                "SELECT * FROM page_version WHERE marker=:m AND version=:v",
                values={"m": marker, "v": version}
            )
        else:
            row = await db.fetch_one(
                "SELECT * FROM page_version WHERE marker=:m ORDER BY version DESC LIMIT 1",
                values={"m": marker}
            )
        return row

    async def list_versions(self, marker: str) -> list:
        """列出所有版本"""
        return await db.fetch_all(
            "SELECT version, status, created_at FROM page_version WHERE marker=:m ORDER BY version DESC",
            values={"m": marker}
        )
```

### 5.3 预览 API

```python
# page_gen/api/routes/page.py
@router.get("/page/{marker}")
async def preview_page(marker: str, version: int = None):
    page = await page_store.get(marker, version)
    if not page:
        raise HTTPException(404, "Page not found")
    return HTMLResponse(content=page["html_content"])

@router.get("/api/v1/page/{marker}/versions")
async def list_versions(marker: str):
    versions = await page_store.list_versions(marker)
    return {"marker": marker, "versions": versions}
```

### 5.4 BOS 对象存储（可选）

如果需要对接百度 BOS 或其他对象存储：

```python
# page_gen/services/storage.py
class BOSStorage:
    """BOS 对象存储适配"""
    def __init__(self, bucket: str, endpoint: str, ak: str, sk: str):
        # 初始化 BOS 客户端
        pass
    
    async def upload(self, key: str, content: bytes) -> str:
        """上传文件，返回 URL"""
        pass
    
    async def download(self, key: str) -> bytes:
        """下载文件"""
        pass
```

> **建议**：Phase 5 前期用本地文件存储，跑通后再换 BOS。原项目用的也是先本地后 BOS 的策略。

### 5.5 验收标准

- [ ] 上传 Excel 文件，解析出字段 schema
- [ ] AI 生成的页面能绑定 Excel 数据（ECharts 图表用真实数据）
- [ ] 每次生成创建新版本，支持版本列表
- [ ] `GET /page/{marker}` 预览页面
- [ ] 支持版本回滚
- [ ] **端到端跑通：上传 Excel → 描述需求 → AI 生成数据驱动页面 → 预览**

---

## 九、Phase 6：迭代增强与生产化

**目标**：安全扫描、迭代编辑、多数据源、SSE 完善、Docker 部署。

**预计工时**：持续迭代

### 6.1 安全扫描（参考原项目 services/security.py）

```python
# page_gen/services/security.py
import re

class SecurityScanner:
    BLOCKED_PATTERNS = [
        r"eval\s*\(",
        r"Function\s*\(",
        r"document\.cookie",
        r"localStorage",
        r"window\.open",
        r"<script[^>]*src=",  # 外部脚本
        r"javascript:",
    ]
    
    def scan(self, html: str) -> dict:
        issues = []
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, html, re.IGNORECASE):
                issues.append(f"Blocked pattern: {pattern}")
        return {"passed": len(issues) == 0, "issues": issues}
```

### 6.2 迭代编辑（参考原项目 agents/direct_editor.py + intent_classifier.py）

```python
# page_gen/agents/intent_classifier.py
class IntentClassifier:
    """意图分类：新建 vs 编辑"""
    def __init__(self, llm: LLMClient):
        self.llm = llm
    
    async def classify(self, prompt: str, existing_html: str = None) -> str:
        if not existing_html:
            return "create"
        # LLM 判断是新建还是编辑
        result = await self.llm.chat([
            {"role": "system", "content": "判断用户意图：create（新建）或 edit（编辑现有页面）"},
            {"role": "user", "content": f"已有页面存在，用户说：{prompt}"}
        ])
        return "edit" if "edit" in result.lower() else "create"
```

### 6.3 SSE 完善事件类型

```python
# 事件类型定义
SSE_EVENTS = {
    "step_start": "步骤开始",
    "step_complete": "步骤完成",
    "step_error": "步骤错误",
    "gate_decision": "门禁决策",
    "contract_result": "契约校验结果",
    "llm_token": "LLM Token 流式输出",
    "progress": "进度更新",
    "completed": "生成完成",
    "failed": "生成失败",
}
```

### 6.4 Docker 部署

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装 Playwright 依赖
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libglib2.0-dev libnss3 libnspr4 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 libxcb1 \
    libxkbcommon0 libx11-6 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .
RUN pip install -e .

EXPOSE 8000
CMD ["uvicorn", "page_gen.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.5 验收标准

- [ ] 安全扫描拦截危险代码
- [ ] 支持对已有页面进行迭代编辑
- [ ] SSE 推送完整事件链
- [ ] Docker 容器一键部署
- [ ] 压力测试通过

---

## 十、技术栈与依赖清单

### 按阶段安装

| 阶段 | 新增依赖 | 用途 |
|------|---------|------|
| Phase 0 | fastapi, uvicorn, sqlalchemy, aiomysql, redis, pydantic, pydantic-settings | 基础框架 |
| Phase 1 | sse-starlette, orjson | SSE 推送 |
| Phase 2 | httpx, tenacity | LLM API 调用 |
| Phase 3 | langgraph, langchain-core, langgraph-checkpoint-mysql | Agent 编排 |
| Phase 4 | playwright, beautifulsoup4 | 浏览器验证 |
| Phase 5 | openpyxl, pandas, jinja2 | 数据服务 |
| Phase 6 | docker | 部署 |

### 智谱 API 替代方案

原项目使用百度自建 GLM-5.1，你用智谱 API 替代：

```python
# 智谱 API 调用示例
# 官方 SDK: pip install zhipuai
# 或直接用 httpx 调用 OpenAI 兼容接口

from openai import AsyncOpenAI  # 智谱支持 OpenAI 兼容接口

client = AsyncOpenAI(
    api_key="your-zhipu-api-key",
    base_url="https://open.bigmodel.cn/api/paas/v4"
)

response = await client.chat.completions.create(
    model="glm-4",  # 或 glm-4-flash, glm-4-plus
    messages=[...],
    temperature=0.3,
)
```

---

## 十一、原项目模块映射表

| 原项目模块 | 对应 Phase | 新项目模块 | 说明 |
|-----------|-----------|-----------|------|
| `page/agents/graph.py` | Phase 3 | `page_gen/agents/graph.py` | LangGraph 状态图 |
| `page/agents/state.py` | Phase 3 | `page_gen/agents/state.py` | GenerationState |
| `page/agents/analyst.py` | Phase 3 | `page_gen/agents/analyzer.py` | 需求分析 |
| `page/agents/designer.py` | Phase 3 | `page_gen/agents/designer.py` | 页面设计 |
| `page/agents/coder.py` | Phase 2-3 | `page_gen/agents/coder.py` | 代码生成 |
| `page/agents/verifier.py` | Phase 3-4 | `page_gen/agents/verifier.py` | 验证 |
| `page/agents/fixer.py` | Phase 3 | `page_gen/agents/fixer.py` | 修复 |
| `page/agents/llm.py` | Phase 2 | `page_gen/agents/llm.py` | LLM 封装 |
| `page/agents/router.py` | Phase 3 | `page_gen/agents/router.py` | 条件路由 |
| `page/agents/intent_classifier.py` | Phase 6 | `page_gen/agents/intent_classifier.py` | 意图分类 |
| `page/agents/direct_editor.py` | Phase 6 | `page_gen/agents/direct_editor.py` | DOM 编辑 |
| `page/harness/orchestrator.py` | Phase 4 | `page_gen/harness/orchestrator.py` | 管道编排 |
| `page/harness/state_machine.py` | Phase 4 | `page_gen/harness/state_machine.py` | 状态机 |
| `page/harness/contracts.py` | Phase 4 | `page_gen/harness/contracts.py` | 契约校验 |
| `page/harness/gates.py` | Phase 4 | `page_gen/harness/gates.py` | 门禁 |
| `page/harness/checkpoint.py` | Phase 4 | `page_gen/harness/checkpoint.py` | Checkpoint |
| `page/harness/repair.py` | Phase 4 | `page_gen/harness/repair.py` | 修复策略 |
| `page/harness/iteration_router.py` | Phase 6 | `page_gen/harness/iteration_router.py` | 迭代路由 |
| `page/harness/validators/` | Phase 4 | `page_gen/harness/validators/` | 验证器 |
| `page/models/tables.py` | Phase 0 | `page_gen/models/tables.py` | 数据库表 |
| `page/models/database.py` | Phase 0 | `page_gen/models/database.py` | DB 连接 |
| `page/models/contracts.py` | Phase 4 | `page_gen/models/contracts.py` | Pydantic 模型 |
| `page/models/enums.py` | Phase 0 | `page_gen/models/enums.py` | 枚举 |
| `page/api/app.py` | Phase 0 | `page_gen/api/app.py` | FastAPI 入口 |
| `page/api/sse.py` | Phase 1 | `page_gen/api/sse.py` | SSE |
| `page/api/routes/` | Phase 1 | `page_gen/api/routes/` | 路由 |
| `page/services/generation_runner.py` | Phase 1-3 | `page_gen/services/generation_runner.py` | 生成运行器 |
| `page/services/session_store.py` | Phase 0 | `page_gen/services/session_store.py` | Session 存储 |
| `page/services/generation_job_store.py` | Phase 0 | `page_gen/services/job_store.py` | 任务存储 |
| `page/services/generation_event_bus.py` | Phase 1 | `page_gen/services/event_bus.py` | 事件总线 |
| `page/services/storage.py` | Phase 5 | `page_gen/services/page_store.py` | 页面存储 |
| `page/services/security.py` | Phase 6 | `page_gen/services/security.py` | 安全扫描 |
| `page/services/image_parser.py` | Phase 5 | `page_gen/services/image_parser.py` | 图片解析 |
| `page/preview/service.py` | Phase 5 | `page_gen/preview/service.py` | 预览服务 |
| `page/config/settings.py` | Phase 0 | `page_gen/config/settings.py` | 配置 |
| `page/core/` | Phase 0 | `page_gen/core/` | 基础工具 |

---

## 十二、关键设计决策对比

| 决策点 | 原项目做法 | 你的重构建议 | 原因 |
|--------|-----------|-------------|------|
| LLM | 百度自建 GLM-5.1 | 智谱 API (GLM-4) | 你有 apiKey，OpenAI 兼容接口 |
| 数据库 | MySQL + SQLAlchemy | 同 | 一致 |
| Checkpoint | langgraph-checkpoint-mysql | 同 | 一致 |
| 浏览器验证 | Playwright | 同 | 一致 |
| 对象存储 | 百度 BOS | 先本地文件，后续按需买 BOS | 降低前期成本 |
| 认证 | UUAP | 可省略或用简单 JWT | 个人项目不需要企业认证 |
| 任务队列 | Celery + Redis | 先用 asyncio + Redis，后续按需加 Celery | 简化前期复杂度 |
| DuckDB | 数据物化 | Phase 5 按需加 | 前期不需要 |
| 部署 | Docker + 百度内网 | Docker + 本地/云服务器 | 个人项目 |
| 配置 | 多环境(.config) | 同（dev/online/sandbox） | 好习惯 |

---

## 总结

这个重构方案的核心思路是**垂直切片**：

1. **每个 Phase 都能跑通**：不是先搭空壳再填肉，而是每个阶段都有端到端的可运行功能
2. **从简单到复杂**：Phase 1 硬编码 → Phase 2 单步 LLM → Phase 3 多 Agent → Phase 4 加护栏 → Phase 5 数据服务 → Phase 6 生产化
3. **与原项目对应**：每个 Phase 都能映射到原项目的模块，方便对照学习
4. **技术栈渐进**：不是一开始就装所有依赖，而是按需引入

建议按顺序执行，每个 Phase 完成后做一次代码 review，对照原项目对应模块学习。遇到不理解的地方，回到原项目看实现细节，这是最好的学习方式。

**祝你重构顺利，Agent 开发落地经验 up up! 🚀**
