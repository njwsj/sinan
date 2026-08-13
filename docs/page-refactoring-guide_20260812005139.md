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

### 1.1 本阶段做什么

端到端路径：

```
POST /api/v1/generate
    → 创建 session（MySQL）
    → 后台异步跑生成流程（5 个步骤）
    → SSE 推送步骤进度
    → 存储硬编码 HTML（MySQL）
    → GET /api/v1/page/{marker} 返回 HTML
```

涉及文件变动：

```
sinan/
├── api/
│   ├── app.py                   ← 修改：注册 generate_router、preview_router
│   ├── deps.py                  ← 修改：加注释说明设计意图
│   └── routes/
│       ├── generate.py          ← Step 1：新建（路由层）
│       └── preview.py           ← Step 5：新建（预览端点）
└── services/
    ├── session_store.py         ← Step 2：新建（MySQL 持久化）
    ├── generation_event_bus.py  ← Step 3：新建（SSE 事件通道）
    └── generation_runner.py     ← Step 4：新建（硬编码生成流程）
```

---

### Step 1：新建 `sinan/api/routes/generate.py`

**做什么**：实现两个路由端点。

- `POST /api/v1/generate`：接收用户的 `prompt` 和 `user_id`，调用 `session_store` 创建数据库记录，然后用 `asyncio.create_task` 把生成任务扔到后台异步执行（注意不能 `await`，否则接口会挂住等生成完才返回），立即返回 `session_id`。
- `GET /api/v1/generate/{session_id}/stream`：SSE 长连接，订阅 `event_bus` 里这个 session 的事件队列，把每一条事件推送给客户端。客户端可以在任意时刻连接，`asyncio.Queue` 会缓存 runner 已经发出但还没被消费的事件。

**注意点**：

- `sse_starlette` 需要在 `requirements.txt` 里已经存在（Phase 0 已装）。
- 路由前缀 `/api/v1` 在 `app.py` 的 `include_router` 里统一加，这里路由本身不带。
- `Body(..., embed=True)` 表示请求体是 `{"prompt": "...", "user_id": "..."}` 形式的 JSON，两个字段并列。

```python
# sinan/api/routes/generate.py
import asyncio
import json
from fastapi import APIRouter, Body
from sse_starlette.sse import EventSourceResponse
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus
from sinan.services.generation_runner import generation_runner

router = APIRouter()


@router.post("/generate")
async def create_generation(
    prompt: str = Body(..., embed=True),
    user_id: str = Body("anonymous", embed=True),
):
    """
    创建生成任务。
    立即返回 session_id，后台异步执行生成流程。
    """
    session = await session_store.create(user_id=user_id, prompt=prompt)
    # create_task 把 runner 扔到事件循环后台，不阻塞当前请求
    asyncio.create_task(generation_runner.start(session.id))
    return {"session_id": session.id, "status": "running"}


@router.get("/generate/{session_id}/stream")
async def stream_generation(session_id: str):
    """
    SSE 长连接，推送该 session 的生成步骤事件。
    事件格式：event: <step_name>  data: {"message": "..."}
    """
    async def event_generator():
        async for evt in event_bus.subscribe(session_id):
            yield {"event": evt.type, "data": json.dumps(evt.data, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
```

---

### Step 2：新建 `sinan/services/session_store.py`

**做什么**：封装对 `GenSession` 表的增删改查，提供三个方法：

- `create(user_id, prompt)`：生成 UUID 作为主键，插入数据库，返回 ORM 对象。
- `get(session_id)`：按主键查询，不存在时返回 `None`。
- `update(session_id, **kwargs)`：通用更新，通过关键字参数批量 setattr，适配后续各种状态字段更新。

**注意点**：

- runner 是后台任务，不在 FastAPI 请求生命周期内，所以不能用 `Depends` 注入 db session，必须每次操作自己 `async with AsyncSessionLocal() as db`，用完自动关闭。
- `db.refresh(session)` 在 commit 之后调用，目的是重新从数据库加载对象，确保返回的对象字段（如 `created_at`）是数据库实际写入的值，避免返回 Python 层面的默认值。

```python
# sinan/services/session_store.py
import uuid
from sqlalchemy import select
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSession
from sinan.models.enums import SessionStatus


class SessionStore:
    async def create(self, user_id: str, prompt: str) -> GenSession:
        """创建新 session，写入数据库，返回 ORM 对象"""
        session_id = str(uuid.uuid4())
        session = GenSession(
            id=session_id,
            user_id=user_id,
            prompt=prompt,
            status=SessionStatus.PENDING,
        )
        async with AsyncSessionLocal() as db:
            db.add(session)
            await db.commit()
            await db.refresh(session)
        return session

    async def get(self, session_id: str) -> GenSession | None:
        """按 ID 查询 session，不存在返回 None"""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenSession).where(GenSession.id == session_id)
            )
            return result.scalar_one_or_none()

    async def update(self, session_id: str, **kwargs) -> None:
        """
        通用字段更新。
        用法示例：await session_store.update(sid, status=SessionStatus.COMPLETED, marker="page_abc")
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GenSession).where(GenSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session is None:
                return
            for key, value in kwargs.items():
                setattr(session, key, value)
            await db.commit()


# 模块级单例，路由和 runner 直接 import 使用
session_store = SessionStore()
```

---

### Step 3：新建 `sinan/services/generation_event_bus.py`

**做什么**：提供一个基于内存 `asyncio.Queue` 的发布/订阅事件通道，用于 runner 和 SSE 路由之间的通信。

架构：内部维护一个 `dict[session_id → asyncio.Queue]`，runner 往 queue 里 `put` 事件，SSE 路由异步 `get` 消费。

- `publish(session_id, event_type, data)`：往对应 queue 推一条事件。
- `publish_done(session_id)`：推一个哨兵对象 `_SENTINEL`，通知 subscriber 生成已结束，关闭 SSE 连接。
- `subscribe(session_id)`：异步生成器，不断从 queue 取事件 yield 出去，遇到 `_SENTINEL` 时停止并清理 queue。

**注意点**：

- `_SENTINEL = object()` 是一个唯一对象，用 `is` 判断，不会误判成正常事件。
- 如果 SSE 客户端在 runner 开始之前就连上，`Queue` 会阻塞在 `await q.get()` 等待，没有竞态问题。
- Phase 1 不处理客户端提前断连的边界情况（queue 会留在内存），Phase 2+ 可加超时清理。

```python
# sinan/services/generation_event_bus.py
import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator

_SENTINEL = object()  # 用于通知 subscriber 生成流程已结束


@dataclass
class GenerationEvent:
    type: str   # 对应步骤名，如 receive / analyze / design / code / verify / host
    data: dict  # 事件内容，至少包含 {"message": "..."}


class GenerationEventBus:
    def __init__(self):
        # session_id → asyncio.Queue[GenerationEvent | _SENTINEL]
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_or_create_queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    async def publish(self, session_id: str, event_type: str, data: dict) -> None:
        """发布一条步骤事件"""
        q = self._get_or_create_queue(session_id)
        await q.put(GenerationEvent(type=event_type, data=data))

    async def publish_done(self, session_id: str) -> None:
        """通知 subscriber 生成已完成，关闭 SSE 流"""
        q = self._get_or_create_queue(session_id)
        await q.put(_SENTINEL)

    async def subscribe(self, session_id: str) -> AsyncGenerator[GenerationEvent, None]:
        """
        异步生成器：持续 yield 该 session 的事件，直到收到终止信号。
        SSE 路由用 async for 消费。
        """
        q = self._get_or_create_queue(session_id)
        while True:
            item = await q.get()
            if item is _SENTINEL:
                # 清理 queue，防止内存泄漏
                self._queues.pop(session_id, None)
                break
            yield item


# 模块级单例
event_bus = GenerationEventBus()
```

---

### Step 4：新建 `sinan/services/generation_runner.py`

**做什么**：Phase 1 的核心，模拟完整的 5 步生成流程（全部硬编码，无 LLM）。

流程：

1. `receive` — 更新 session 状态为 RUNNING，推送"接收需求"事件
2. `analyze` — 推送"分析需求"事件
3. `design` — 推送"设计页面结构"事件
4. `code` — 调用 `_template_html(prompt)` 生成硬编码 HTML，推送"生成页面"事件
5. `verify` — 推送"验证通过"事件
6. `host`（不计入步骤表）— 把 HTML 写入 `PageVersion` 表，更新 session 字段，推送托管完成事件，最后调用 `publish_done` 关闭 SSE

每个步骤都会：

- 调用 `event_bus.publish` 推送 SSE 事件
- `asyncio.sleep(0.5)` 模拟耗时（Phase 2 替换为真实 LLM 调用）
- 调用 `_write_step` 写一条 `GenSessionStep` 记录到数据库

**注意点**：

- `_template_html` 里有 f-string + CSS `{{}}` 的双括号写法，是为了转义 f-string 里的花括号，写出来的 HTML 里是单括号 `{}`，这是正常的。
- runner 是后台协程，**不能用断点调试**（调试器会冻住事件循环，SSE 无法收到数据），用 `print` 观察状态即可。
- `_save_page` 里 `created_by` 传 `session_id`，Phase 2 完善用户体系后再改。

```python
# sinan/services/generation_runner.py
import asyncio
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep, PageVersion
from sinan.models.enums import SessionStatus, PageStatus
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus


class GenerationRunner:

    async def start(self, session_id: str) -> None:
        """
        后台异步执行生成流程。
        由 generate 路由通过 asyncio.create_task 启动，不阻塞请求。
        """
        await session_store.update(session_id, status=SessionStatus.RUNNING)

        # 步骤定义：(step_name, 推送给前端的消息)
        steps = [
            ("receive", "正在接收需求..."),
            ("analyze", "正在分析需求..."),
            ("design",  "正在设计页面结构..."),
            ("code",    "正在生成页面..."),
            ("verify",  "验证通过"),
        ]

        html = ""
        for step_name, message in steps:
            await event_bus.publish(session_id, step_name, {"message": message})
            await asyncio.sleep(0.5)  # 模拟耗时，Phase 2 替换为 LLM 调用
            await self._write_step(session_id, step_name, message)

            if step_name == "code":
                # code 步骤：生成硬编码 HTML
                session = await session_store.get(session_id)
                prompt = session.prompt if session else ""
                html = self._template_html(prompt)

        # 托管：写 page_version 表，更新 session
        marker = f"page_{session_id[:8]}"
        version = 1
        await self._save_page(marker, version, html, created_by=session_id)
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED,
            marker=marker,
            version=version,
            preview_url=f"/api/v1/page/{marker}",
        )

        # 推送托管完成事件，再关闭 SSE 流
        await event_bus.publish(
            session_id,
            "host",
            {"message": f"页面已生成，预览地址: /api/v1/page/{marker}", "url": f"/api/v1/page/{marker}"},
        )
        await event_bus.publish_done(session_id)

    async def _write_step(self, session_id: str, step: str, message: str) -> None:
        """把步骤执行记录写入 gen_session_step 表"""
        record = GenSessionStep(
            session_id=session_id,
            step=step,
            direction="output",
            output_data={"message": message},
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()

    async def _save_page(self, marker: str, version: int, html: str, created_by: str) -> None:
        """把生成的 HTML 存入 page_version 表"""
        record = PageVersion(
            marker=marker,
            version=version,
            html_content=html,
            status=PageStatus.PUBLISHED,
            created_by=created_by,
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()

    def _template_html(self, prompt: str) -> str:
        """
        Phase 1 硬编码 HTML 模板，把 prompt 嵌入标题。
        Phase 2 替换为 LLM 生成的真实 HTML。
        注意：CSS 里的花括号需要双写 {{}} 以转义 f-string。
        """
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>生成页面</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    margin: 0; padding: 40px; background: #f5f7fa; color: #333;
  }}
  .card {{
    background: #fff; border-radius: 12px; padding: 32px;
    box-shadow: 0 2px 12px rgba(0,0,0,.08); max-width: 800px; margin: 0 auto;
  }}
  h1 {{ font-size: 24px; margin-bottom: 8px; color: #1a1a2e; }}
  p  {{ color: #666; line-height: 1.6; }}
  .badge {{
    display: inline-block; background: #e8f4fd; color: #1677ff;
    padding: 4px 12px; border-radius: 20px; font-size: 13px; margin-top: 16px;
  }}
</style>
</head>
<body>
  <div class="card">
    <h1>Hello HTML</h1>
    <p>你的需求：<strong>{prompt}</strong></p>
    <p>这是 Phase 1 硬编码模板页面，Phase 2 将接入 LLM 生成真实内容。</p>
    <span class="badge">Phase 1 · 硬编码原型</span>
  </div>
</body>
</html>"""


# 模块级单例
generation_runner = GenerationRunner()
```

---

### Step 5：新建 `sinan/api/routes/preview.py`

**做什么**：实现页面预览接口 `GET /api/v1/page/{marker}`。

从 `PageVersion` 表查询该 marker 下 `version` 最大的记录，把 `html_content` 直接以 `text/html` 返回，浏览器打开就能渲染。

**注意点**：

- `order_by(desc(PageVersion.version)).limit(1)` 而不是 `order_by(desc(PageVersion.id))`，因为 version 才是业务版本号，语义更准确。
- 不存在时返回 404 JSON，而不是抛异常，这样 curl 测试时信息更清晰。
- `response_class=HTMLResponse` 告诉 FastAPI 和 OpenAPI 文档这个接口返回 HTML，不是 JSON。

```python
# sinan/api/routes/preview.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, desc
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import PageVersion

router = APIRouter()


@router.get("/page/{marker}", response_class=HTMLResponse)
async def preview_page(marker: str):
    """
    返回指定 marker 的最新版本 HTML 页面。
    直接在浏览器渲染，media_type 为 text/html。
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PageVersion)
            .where(PageVersion.marker == marker)
            .order_by(desc(PageVersion.version))
            .limit(1)
        )
        page = result.scalar_one_or_none()

    if page is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"页面 '{marker}' 不存在"}
        )

    return HTMLResponse(content=page.html_content)
```

---

### Step 6：修改 `sinan/api/app.py`

**做什么**：把新增的两个 router 注册进 FastAPI 应用，统一加 `/api/v1` 前缀。

**注意点**：只改 `import` 和 `include_router`，其余逻辑不动。

```python
# sinan/api/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sinan.config.settings import settings
from sinan.core.logging import setup_logging
from sinan.models.database import init_db
from sinan.api.routes.health import router as health_router
from sinan.api.routes.generate import router as generate_router
from sinan.api.routes.preview import router as preview_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.debug)
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)                          # /health（无前缀）
    app.include_router(generate_router, prefix="/api/v1")     # /api/v1/generate
    app.include_router(preview_router, prefix="/api/v1")      # /api/v1/page/{marker}
    return app


app = create_app()
```

---

### Step 7：修改 `sinan/api/deps.py`

**做什么**：Phase 1 所有服务用模块级单例，路由直接 import，`deps.py` 暂时不需要任何实质内容。留下注释说明设计意图，Phase 2+ 如果需要请求级 db session 注入再来扩充。

```python
# sinan/api/deps.py
#
# Phase 1: 服务以模块级单例暴露，路由直接 import 使用：
#   from sinan.services.session_store import session_store
#   from sinan.services.generation_event_bus import event_bus
#   from sinan.services.generation_runner import generation_runner
#
# Phase 2+: 如需请求级 db session 注入，在此添加：
#   async def get_db() -> AsyncGenerator[AsyncSession, None]:
#       async with AsyncSessionLocal() as session:
#           yield session
```

---

### 1.2 验收标准

```bash
# 启动服务
python -m sinan

# 1. 创建任务
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "做一个 GPU 使用率看板", "user_id": "test_user"}'
# 预期: {"session_id": "xxxxxxxx-...", "status": "running"}

# 2. SSE 订阅（另开终端，替换 SESSION_ID）
curl -N http://localhost:8000/api/v1/generate/SESSION_ID/stream
# 预期: 收到 receive / analyze / design / code / verify / host 6 条事件后连接关闭

# 3. 预览页面（取 session_id 前 8 位替换 XXXXXXXX）
open http://localhost:8000/api/v1/page/page_XXXXXXXX
# 预期: 浏览器渲染出 "Hello HTML" 页面，显示你输入的 prompt
```

- [ ] `POST /api/v1/generate` 返回 `session_id`，接口立即返回不阻塞
- [ ] SSE 流推送 6 条事件（receive / analyze / design / code / verify / host）后连接自动关闭
- [ ] `GET /api/v1/page/{marker}` 浏览器可直接渲染 HTML 页面
- [ ] `gen_session` 表：`status = completed`，`marker` 和 `preview_url` 有值
- [ ] `gen_session_step` 表：5 条步骤记录（receive/analyze/design/code/verify）
- [ ] `page_version` 表：1 条记录，`html_content` 有完整 HTML 内容
- [ ] **端到端跑通，能在浏览器看到一个 HTML 页面**

---

## 五、Phase 2：接入 LLM — 让 AI 生成页面

**目标**：用智谱 API 替换硬编码生成器，实现"描述→HTML"的单步 LLM 生成。

**预计工时**：2-3 天

**涉及文件变动**：

```
sinan/
├── agents/
│   ├── __init__.py          ← Step 3：新建（空文件，让目录成为 Python 包）
│   ├── llm.py               ← Step 4：新建（LLM 客户端封装）
│   └── coder.py             ← Step 5：新建（单步 Coder Agent）
└── services/
    └── generation_runner.py ← Step 6：修改（替换硬编码为真实 LLM 调用）
```

---

### Step 1：确认依赖已就绪（无需操作）

`requirements.txt` 里已经有 `httpx>=0.27.0` 和 `tenacity>=9.0.0`，不需要新增。

只需确认已安装到当前环境：

```bash
pip show httpx tenacity
```

两个包都有输出（显示 Name/Version）说明就绪。如果提示 `Package(s) not found`，执行：

```bash
pip install httpx tenacity
```

---

### Step 2：填写 `.env` 里的 `LLM_API_KEY`

**为什么先做这步**：`llm.py` 写好后第一件事就是测试能否跑通，key 没填的话测试直接收到 401，浪费排查时间。

打开项目根目录的 `.env` 文件，找到这一行：

```
LLM_API_KEY=
```

改为：

```
LLM_API_KEY=你在智谱开放平台申请的真实 key
```

其余配置已经正确，不需要改：

```
LLM_MODEL=glm-4
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
```

---

### Step 3：创建 `sinan/agents/` 目录和 `__init__.py`

`sinan/` 下目前没有 `agents/` 目录。Phase 2 开始把 LLM 封装和 Agent 都放在这里，与 Phase 3 的多 Agent 体系保持一致。

新建两个文件：

**`sinan/agents/__init__.py`**（空文件）：

```python
```

（内容为空，让 Python 把这个目录识别为包。）

---

### Step 4：新建 `sinan/agents/llm.py`

**设计说明**：

- **为什么用 `httpx` 而不是官方 SDK**：智谱官方 Python SDK 是同步的，整个项目是 `asyncio` 异步体系，同步调用会阻塞事件循环，必须用异步 HTTP 客户端直接调。
- **为什么用 `tenacity` 重试**：LLM API 偶发超时或 5xx 是正常现象。失败后等 1 秒重试，最多 3 次（含第一次），不会因偶发抖动让整个流程失败。`reraise=True` 表示 3 次全部失败后把原始异常向上抛，让调用方处理。
- **`timeout=120`**：`glm-4` 生成复杂 HTML 可能需要 30-60 秒，默认 5 秒超时会直接报错，120 秒是保守值。
- **`LLMClient` 不做单例**：它只持有配置，不持有连接，每次调用时新建 `httpx.AsyncClient`。单例由上层 `generation_runner.py` 管理。

**文件：`sinan/agents/llm.py`**

```python
# sinan/agents/llm.py
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class LLMClient:
    """
    智谱 API 的异步封装。
    使用 httpx 直接调用 /chat/completions，tenacity 做自动重试。
    """

    def __init__(self, api_key: str, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """
        发送 chat 请求，返回模型回复的文本内容。
        失败时自动重试，最多 3 次，每次等待 1-10 秒。
        reraise=True 表示 3 次全部失败后把原始异常向上抛，让调用方处理。
        """
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
```

---

### Step 5：新建 `sinan/agents/coder.py`

**设计说明**：

- **System prompt 要明确说"返回纯 HTML"**：LLM 默认会把代码包在 ` ```html ... ``` ` 里，这是 Markdown 格式，直接存入数据库再渲染会显示原始字符串。必须在 prompt 里明确禁止，并在代码里再做一次剥离兜底。
- **`_strip_markdown` 覆盖多种变体**：LLM 输出不稳定，有时是 ` ```html\n`，有时是 ` ```HTML\n`，代码里覆盖了常见情况。
- **`temperature=0.3`**：生成代码场景用低温度，减少随机性，让输出更符合 HTML 语法规范。
- **System prompt 要求用 ECharts 做图表**：生成的 HTML 自动引入 ECharts CDN，适合做数据看板类需求，与 Phase 3 多 Agent 体系保持一致。

**文件：`sinan/agents/coder.py`**

```python
# sinan/agents/coder.py
from sinan.agents.llm import LLMClient


class CoderAgent:
    """
    Phase 2 单步 Coder：直接把用户描述翻译成 HTML 页面。
    Phase 3 会拆成 Analyzer → Designer → Coder → Verifier → Fixer 多步流水线。
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def generate(self, prompt: str) -> str:
        """
        根据用户描述生成完整 HTML 页面。
        返回去除 markdown 包裹的纯 HTML 字符串。
        """
        system_prompt = """你是一个专业的前端页面生成专家。
根据用户的需求，生成一个完整、可直接在浏览器运行的 HTML 页面。

要求：
1. 返回纯 HTML 文本，不要任何 markdown 格式（不要 ```html 代码块）
2. 所有 CSS 和 JavaScript 都内联在 HTML 文件里，不引用外部本地文件
3. 需要图表时使用 ECharts（通过 CDN 引入：https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js）
4. 使用响应式布局，适配不同屏幕宽度
5. 使用现代化 UI 风格，配色专业
6. 页面需要有真实的示例数据，不要空占位符
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        html = await self.llm.chat(messages, temperature=0.3)
        html = self._strip_markdown(html)
        return html

    def _strip_markdown(self, text: str) -> str:
        """去除 LLM 可能在 HTML 外面套的 markdown 代码块包裹。"""
        text = text.strip()

        # 处理 ```html 或 ```HTML 开头
        for prefix in ("```html\n", "```HTML\n", "```html", "```HTML"):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break

        # 处理结尾的 ```
        if text.endswith("```"):
            text = text[:-3]

        return text.strip()
```

---

### Step 6：修改 `sinan/services/generation_runner.py`

**改动点说明**：

1. **构造函数新增 `llm` 和 `coder` 参数**：Runner 不负责创建 LLM 客户端，由外部注入（依赖注入），方便测试和未来替换。
2. **步骤精简为 3 步**：`receive`（接收需求）→ `code`（AI 生成中）→ `verify`（完成）。原来 Phase 1 的 `analyze` 和 `design` 是假步骤，去掉更诚实，Phase 3 会有真实的多 Agent 步骤。
3. **`code` 步骤调 `await self.coder.generate(prompt)`**：真实 LLM 调用，会阻塞 30-60 秒。在调用之前先推一次 `code` 事件告诉前端"AI 正在生成"，让用户知道在等待而不是卡死。
4. **加 `try/except` 错误处理**：LLM 调用可能因 key 无效、网络超时、API 限流等失败。失败时：推送 `error` 事件（前端展示错误提示）、更新 session 状态为 `FAILED`、调用 `publish_done` 关闭 SSE 流（否则前端会一直挂着等待）。
5. **模块底部单例初始化方式改变**：Phase 1 是 `GenerationRunner()`（无参数）。Phase 2 把 `settings` 里的配置传进去，初始化 `LLMClient` 和 `CoderAgent`。

**完整文件 `sinan/services/generation_runner.py`**（替换 Phase 1 的版本）：

```python
# sinan/services/generation_runner.py
import asyncio
import logging

from sinan.agents.coder import CoderAgent
from sinan.agents.llm import LLMClient
from sinan.config.settings import settings
from sinan.models.database import AsyncSessionLocal
from sinan.models.enums import PageStatus, SessionStatus
from sinan.models.tables import GenSessionStep, PageVersion
from sinan.services.generation_event_bus import event_bus
from sinan.services.session_store import session_store

logger = logging.getLogger(__name__)


class GenerationRunner:
    """
    Phase 2：用真实 LLM 调用替换 Phase 1 的硬编码模板。
    流程：receive → code（LLM 生成）→ verify → host
    """

    def __init__(self, llm: LLMClient, coder: CoderAgent):
        self.llm = llm
        self.coder = coder

    async def start(self, session_id: str) -> None:
        """
        后台异步执行生成流程。
        由 generate 路由通过 asyncio.create_task 启动，不阻塞请求。
        """
        await session_store.update(session_id, status=SessionStatus.RUNNING)

        try:
            # 步骤 1：接收需求
            await event_bus.publish(session_id, "receive", {"message": "正在接收需求..."})
            await self._write_step(session_id, "receive", "正在接收需求...")

            # 获取用户输入的 prompt
            session = await session_store.get(session_id)
            prompt = session.prompt if session else ""

            # 步骤 2：LLM 生成 HTML（耗时步骤，先推事件告知前端）
            await event_bus.publish(session_id, "code", {"message": "AI 正在生成页面，请稍候..."})
            html = await self.coder.generate(prompt)
            await self._write_step(session_id, "code", "AI 生成完成")

            # 步骤 3：验证通过
            await event_bus.publish(session_id, "verify", {"message": "验证通过"})
            await self._write_step(session_id, "verify", "验证通过")

        except Exception as e:
            logger.exception("generation failed for session %s", session_id)
            await event_bus.publish(session_id, "error", {"message": f"生成失败：{e}"})
            await session_store.update(session_id, status=SessionStatus.FAILED)
            await event_bus.publish_done(session_id)
            return

        # 托管：写 page_version 表，更新 session
        marker = f"page_{session_id[:8]}"
        version = 1
        await self._save_page(marker, version, html, created_by=session_id)
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED,
            marker=marker,
            version=version,
            preview_url=f"/api/v1/page/{marker}",
        )

        # 推送托管完成事件，再关闭 SSE 流
        await event_bus.publish(
            session_id,
            "host",
            {
                "message": f"页面已生成，预览地址: /api/v1/page/{marker}",
                "url": f"/api/v1/page/{marker}",
            },
        )
        await event_bus.publish_done(session_id)

    async def _write_step(self, session_id: str, step: str, message: str) -> None:
        """把步骤执行记录写入 gen_session_step 表。"""
        record = GenSessionStep(
            session_id=session_id,
            step=step,
            direction="output",
            output_data={"message": message},
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()

    async def _save_page(self, marker: str, version: int, html: str, created_by: str) -> None:
        """把生成的 HTML 存入 page_version 表。"""
        record = PageVersion(
            marker=marker,
            version=version,
            html_content=html,
            status=PageStatus.PUBLISHED,
            created_by=created_by,
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()


# 模块级单例：用 settings 里的配置初始化 LLM 和 CoderAgent
_llm = LLMClient(
    api_key=settings.llm_api_key,
    model=settings.llm_model,
    base_url=settings.llm_base_url,
)
_coder = CoderAgent(_llm)
generation_runner = GenerationRunner(_llm, _coder)
```

---

### Step 7：端到端验证

**7.1 先单独测 LLM 连通性**

在项目根目录新建临时测试脚本（验完删掉）：

```python
# test_llm.py（临时脚本，验完删掉）
import asyncio
from sinan.agents.llm import LLMClient
from sinan.config.settings import settings

async def main():
    client = LLMClient(settings.llm_api_key, settings.llm_model, settings.llm_base_url)
    result = await client.chat([{"role": "user", "content": "说一句话：你好"}])
    print(result)

asyncio.run(main())
```

```bash
python test_llm.py
```

预期结果：打印出 LLM 的回复，例如"你好！有什么我可以帮助你的？"  
报 401 → `LLM_API_KEY` 没填对，回到 Step 2  
报 ConnectError/超时 → 网络问题，检查 `LLM_BASE_URL` 是否可达

**7.2 单独测 CoderAgent**

```python
# test_coder.py（临时脚本，验完删掉）
import asyncio
from sinan.agents.llm import LLMClient
from sinan.agents.coder import CoderAgent
from sinan.config.settings import settings

async def main():
    llm = LLMClient(settings.llm_api_key, settings.llm_model, settings.llm_base_url)
    coder = CoderAgent(llm)
    html = await coder.generate("做一个简单的 Hello World 页面")
    print(html[:500])  # 打印前 500 字符
    print("---")
    print("是否以 <!DOCTYPE 开头:", html.strip().startswith("<!DOCTYPE"))

asyncio.run(main())
```

预期结果：打印出 HTML 前 500 字符，且最后一行打印 `True`（说明 markdown 剥离成功）  
最后一行打印 `False` → LLM 还是包了 markdown，看实际输出格式，调整 `_strip_markdown` 里的 prefix 列表

**7.3 启动服务，跑完整流程**

```bash
sinan serve
```

另开终端，发起生成请求：

```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "做一个 GPU 使用率监控看板"}'
```

拿到 `session_id`，连 SSE 流：

```bash
curl -N http://localhost:8000/api/v1/generate/{session_id}/stream
```

预期的 SSE 事件顺序：

```
event: receive
data: {"message": "正在接收需求..."}

event: code
data: {"message": "AI 正在生成页面，请稍候..."}

（等待 30-60 秒，LLM 生成中）

event: verify
data: {"message": "验证通过"}

event: host
data: {"message": "页面已生成，预览地址: /api/v1/page/page_xxxxxxxx", "url": "/api/v1/page/page_xxxxxxxx"}
```

**7.4 浏览器预览**

拿到 host 事件里的 `url`，浏览器打开：

```
http://localhost:8000/api/v1/page/page_xxxxxxxx
```

看到 AI 生成的真实 HTML 页面，Phase 2 验收完成。

---

### 常见坑

| 坑 | 说明 |
|----|------|
| LLM 超时 | `glm-4` 生成复杂 HTML 可能要 30-60 秒，`timeout` 不够会断连 |
| SSE 提前关闭 | 前端如果 30 秒内没收到事件会断开，LLM 生成期间可以每隔几秒推一个 `ping` 事件保活 |
| HTML 里有 markdown 包裹 | `_strip_markdown` 要覆盖 ` ```html\n` 和 ` ```\n` 的变体 |
| `settings.llm_api_key` 为空 | 没填 `.env` 的话，httpx 报 401 |

---

### 2.4 验收标准

- [ ] 输入"做一个 GPU 使用率看板"，AI 返回真实 HTML 页面
- [ ] SSE 流按顺序推送 `receive` → `code` → `verify` → `host` 事件
- [ ] LLM 调用失败时推送 `error` 事件，session 状态变为 `FAILED`，SSE 流正常关闭
- [ ] 页面可在浏览器中预览
- [ ] **端到端跑通：自然语言 → AI 生成 → 预览页面**

---

## 六、Phase 3：LangGraph 多 Agent 编排

**目标**：把现在 `CoderAgent` 的单步生成，拆成 `Analyzer → Designer → Coder → Verifier` 四个串行 Agent 节点，用 LangGraph 编排。

---

### Step 1：安装依赖

在 `requirements.txt` 里加入 LangGraph：

```
langgraph>=0.2.0
```

然后执行：

```bash
pip install langgraph
```

**说明**：LangGraph 是 LangChain 生态下的图编排框架，用有向图描述 Agent 之间的流转关系。`langgraph>=0.2.0` 这个版本引入了 `StateGraph`，API 稳定。

---

### Step 2：定义共享状态（State）

新建文件 `sinan/agents/state.py`：

```python
# sinan/agents/state.py
from typing import TypedDict


class PageGenState(TypedDict):
    """LangGraph 节点之间共享的流水线状态。"""

    # 输入
    prompt: str

    # Analyzer 产出
    requirements: str       # 结构化需求：功能列表、交互要点

    # Designer 产出
    design: str             # 设计方案：布局结构、配色方案、组件清单

    # Coder 产出
    html: str               # 生成的 HTML 页面

    # Verifier 产出
    verified: bool          # 是否通过验证
    verify_message: str     # 验证结论或错误描述
```

**说明**：LangGraph 的 `StateGraph` 要求你先定义一个 `TypedDict` 作为节点间传递的"共享黑板"。每个节点接收完整 state，返回它要更新的字段（dict），框架会自动合并。

---

### Step 3：实现 Analyzer Agent

新建文件 `sinan/agents/analyzer.py`：

```python
# sinan/agents/analyzer.py
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState

SYSTEM_PROMPT = """你是一个需求分析专家。
分析用户的页面需求，输出结构化的需求清单。

输出格式（纯文本，不要 markdown）：
1. 核心功能列表（每条一行）
2. 数据展示要求
3. 交互要点
4. 特殊约束（如：必须用 ECharts、响应式等）

直接输出分析结果，不要任何前缀说明。"""


class AnalyzerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": state["prompt"]},
        ]
        requirements = await self.llm.chat(messages, temperature=0.3)
        return {"requirements": requirements}
```

**说明**：每个 Agent 的 `run` 方法接收完整 state，只返回它负责更新的字段（这里是 `requirements`）。温度用 0.3 保证分析结果确定性。

---

### Step 4：实现 Designer Agent

新建文件 `sinan/agents/designer.py`：

```python
# sinan/agents/designer.py
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState

SYSTEM_PROMPT = """你是一个前端 UI 设计师。
根据需求分析结果，输出具体的页面设计方案。

输出格式（纯文本，不要 markdown）：
1. 整体布局描述（如：顶部导航 + 左侧面板 + 右侧主区域）
2. 配色方案（主色、辅色、背景色的具体十六进制值）
3. 组件清单（每个组件一行，说明用途和位置）
4. 数据展示方式（表格/图表/卡片，及图表类型）

直接输出设计方案，不要任何前缀说明。"""


class DesignerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        user_content = f"用户需求：\n{state['prompt']}\n\n需求分析：\n{state['requirements']}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        design = await self.llm.chat(messages, temperature=0.5)
        return {"design": design}
```

**说明**：Designer 同时读取原始 `prompt` 和 Analyzer 输出的 `requirements`，让设计方案有完整上下文。

---

### Step 5：改造 Coder Agent

用 LangGraph 节点格式改写 `sinan/agents/coder.py`（保留原有 `_strip_markdown`，改造 `generate` → `run`）：

```python
# sinan/agents/coder.py
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState

SYSTEM_PROMPT = """你是一个前端页面生成专家。
根据需求分析和设计方案，生成一个完整的、可直接在浏览器运行的 HTML 页面。

要求：
1. 页面必须是完整的 HTML 文档，包含 <!DOCTYPE html>、<head>、<body>
2. CSS 全部内联在 <style> 标签中，不依赖外部 CSS 文件
3. JavaScript 全部内联在 <script> 标签中
4. 如果需要图表，使用 ECharts（通过 CDN 引入：https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js）
5. 响应式布局，适配不同屏幕宽度
6. 现代化 UI 风格，配色协调，有适当的间距和层次感
7. 只返回纯 HTML 代码，不要任何 markdown 格式（不要 ```html 包裹）
8. 不要任何解释文字，直接输出 HTML"""


class CoderAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        user_content = (
            f"用户需求：\n{state['prompt']}\n\n"
            f"需求分析：\n{state['requirements']}\n\n"
            f"设计方案：\n{state['design']}"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        html = await self.llm.chat(messages, temperature=0.3)
        return {"html": self._strip_markdown(html)}

    def _strip_markdown(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```html"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()
```

**说明**：Coder 现在拿到三个上下文（prompt + requirements + design），生成质量更高。`generate` 方法改名为 `run` 以统一节点接口。

---

### Step 6：实现 Verifier Agent

新建文件 `sinan/agents/verifier.py`：

```python
# sinan/agents/verifier.py
from sinan.agents.state import PageGenState


class VerifierAgent:
    """
    轻量级 HTML 结构校验，不调用 LLM。
    只做必要性检查：有 DOCTYPE、有 html 标签、有 body 标签、长度达标。
    """

    MIN_HTML_LENGTH = 200

    async def run(self, state: PageGenState) -> dict:
        html = state.get("html", "")
        errors = []

        if "<!DOCTYPE html>" not in html.upper()[:200]:
            errors.append("缺少 <!DOCTYPE html>")
        if "<html" not in html.lower():
            errors.append("缺少 <html> 标签")
        if "<body" not in html.lower():
            errors.append("缺少 <body> 标签")
        if len(html) < self.MIN_HTML_LENGTH:
            errors.append(f"HTML 内容过短（{len(html)} 字符），疑似生成失败")

        if errors:
            return {"verified": False, "verify_message": "；".join(errors)}
        return {"verified": True, "verify_message": "校验通过"}
```

**说明**：Phase 3 的 Verifier 用规则校验（不消耗 token），Phase 4 可以升级成 LLM-based 校验。这里不抛异常，只设 `verified` 标志，由图的条件边决定后续走向。

---

### Step 7：用 LangGraph 组装图

新建文件 `sinan/agents/graph.py`：

```python
# sinan/agents/graph.py
from langgraph.graph import StateGraph, END
from sinan.agents.state import PageGenState
from sinan.agents.analyzer import AnalyzerAgent
from sinan.agents.designer import DesignerAgent
from sinan.agents.coder import CoderAgent
from sinan.agents.verifier import VerifierAgent
from sinan.agents.llm import LLMClient


def build_graph(llm: LLMClient) -> StateGraph:
    analyzer = AnalyzerAgent(llm)
    designer = DesignerAgent(llm)
    coder = CoderAgent(llm)
    verifier = VerifierAgent()

    graph = StateGraph(PageGenState)

    # 注册节点：节点名 → 异步函数（接收 state，返回更新 dict）
    graph.add_node("analyze", analyzer.run)
    graph.add_node("design", designer.run)
    graph.add_node("code", coder.run)
    graph.add_node("verify", verifier.run)

    # 串行边
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "design")
    graph.add_edge("design", "code")
    graph.add_edge("code", "verify")

    # 条件边：验证通过 → END，验证失败 → 直接 END（Phase 3 不做修复，Phase 4 接 Fixer）
    graph.add_conditional_edges(
        "verify",
        lambda state: "end" if state["verified"] else "end",  # Phase 4 改为走 fixer
        {"end": END},
    )

    return graph.compile()
```

**说明**：`StateGraph` 的工作流：注册节点 → 连边 → `compile()` 生成可执行图。`add_conditional_edges` 是扩展点，Phase 4 把 lambda 里的 `"end"` 改成 `"fix"` 就能接入 Fixer。

---

### Step 8：更新 GenerationRunner

用图执行替换单步 `CoderAgent` 调用，修改 `sinan/services/generation_runner.py`：

```python
# sinan/services/generation_runner.py
import logging
from sinan.agents.llm import LLMClient
from sinan.agents.graph import build_graph
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep, PageVersion
from sinan.models.enums import SessionStatus, PageStatus
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus
from sinan.config.settings import settings

logger = logging.getLogger(__name__)


class GenerationRunner:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.graph = build_graph(llm)

    async def start(self, session_id: str) -> None:
        await session_store.update(session_id, status=SessionStatus.RUNNING)

        try:
            session = await session_store.get(session_id)
            prompt = session.prompt if session else ""

            # 步骤事件：analyze
            await event_bus.publish(session_id, "analyze", {"message": "正在分析需求..."})
            await self._write_step(session_id, "analyze", "开始需求分析")

            # 步骤事件：design
            await event_bus.publish(session_id, "design", {"message": "正在制定设计方案..."})
            await self._write_step(session_id, "design", "开始设计")

            # 步骤事件：code
            await event_bus.publish(session_id, "code", {"message": "AI 正在生成页面代码..."})
            await self._write_step(session_id, "code", "开始生成")

            # 执行 LangGraph 图（内部串行执行 analyze → design → code → verify）
            final_state = await self.graph.ainvoke({"prompt": prompt})

            await self._write_step(session_id, "verify", final_state["verify_message"])
            await event_bus.publish(
                session_id, "verify", {"message": final_state["verify_message"]}
            )

            if not final_state["verified"]:
                raise ValueError(final_state["verify_message"])

            html = final_state["html"]

        except Exception as e:
            logger.exception("generation failed for session %s", session_id)
            await event_bus.publish(session_id, "error", {"message": f"生成失败：{e}"})
            await session_store.update(session_id, status=SessionStatus.FAILED)
            await event_bus.publish_done(session_id)
            return

        marker = f"page_{session_id[:8]}"
        version = 1
        await self._save_page(marker, version, html, created_by=session_id)
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED,
            marker=marker,
            version=version,
            preview_url=f"/api/v1/page/{marker}",
        )
        await event_bus.publish(
            session_id,
            "host",
            {"message": f"页面已生成，预览地址: /api/v1/page/{marker}", "url": f"/api/v1/page/{marker}"},
        )
        await event_bus.publish_done(session_id)

    async def _write_step(self, session_id: str, step: str, message: str) -> None:
        record = GenSessionStep(
            session_id=session_id,
            step=step,
            direction="output",
            output_data={"message": message},
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()

    async def _save_page(self, marker: str, version: int, html: str, created_by: str) -> None:
        record = PageVersion(
            marker=marker,
            version=version,
            html_content=html,
            status=PageStatus.PUBLISHED,
            created_by=created_by,
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()


_llm = LLMClient(
    api_key=settings.llm_api_key,
    model=settings.llm_model,
    base_url=settings.llm_base_url,
)
generation_runner = GenerationRunner(_llm)
```

**说明**：`graph.ainvoke()` 是 LangGraph 的异步执行入口，它会按图的边顺序依次执行所有节点，最终返回合并后的完整 state。Runner 不再需要持有 `CoderAgent` 引用，只持有 `graph`。

---

### Step 9：更新 agents `__init__.py` 导出

修改 `sinan/agents/__init__.py`，把新增的 Agent 都导出：

```python
# sinan/agents/__init__.py
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState
from sinan.agents.analyzer import AnalyzerAgent
from sinan.agents.designer import DesignerAgent
from sinan.agents.coder import CoderAgent
from sinan.agents.verifier import VerifierAgent
from sinan.agents.graph import build_graph
```

---

### Step 10：验收测试

启动服务后，用 curl 测试完整流程：

```bash
# 1. 发起生成请求
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "做一个 GPU 使用率监控看板，展示 8 张卡的实时使用率折线图"}'

# 返回 {"session_id": "xxx", "status": "running"}

# 2. 订阅 SSE 流（把 xxx 换成上面返回的 session_id）
curl -N http://localhost:8000/api/v1/generate/xxx/stream
```

预期 SSE 输出顺序：

```
event: analyze
data: {"message": "正在分析需求..."}

event: design
data: {"message": "正在制定设计方案..."}

event: code
data: {"message": "AI 正在生成页面代码..."}

event: verify
data: {"message": "校验通过"}

event: host
data: {"message": "页面已生成，预览地址: /api/v1/page/page_xxx", "url": "/api/v1/page/page_xxx"}

event: done
data: {}
```

---

### 文件变更汇总

| 操作 | 文件 |
|------|------|
| 新建 | `sinan/agents/state.py` |
| 新建 | `sinan/agents/analyzer.py` |
| 新建 | `sinan/agents/designer.py` |
| 新建 | `sinan/agents/verifier.py` |
| 新建 | `sinan/agents/graph.py` |
| 修改 | `sinan/agents/coder.py`（`generate` → `run`，入参加 design/requirements） |
| 修改 | `sinan/services/generation_runner.py`（用 graph.ainvoke 替换 coder.generate） |
| 修改 | `sinan/agents/__init__.py`（补充导出） |
| 修改 | `requirements.txt`（加 `langgraph>=0.2.0`） |

Phase 3 完成后，`verified=False` 的条件边留着，Phase 4 只需把 `graph.py` 里的条件边 lambda 改成路由到 `Fixer` 节点，整个流水线自然延伸。

---

## 七、Phase 4：Harness 工程化 — 质量护栏

**目标**：在 Phase 3 的 `Analyzer→Designer→Coder→Verifier` 流水线基础上，加入：
1. **Fixer Agent**：验证失败时自动修复 HTML（最多 3 轮）
2. **门禁节点（Gate）**：每步后校验输出质量，决定 proceed / retry / fix / block
3. **契约模型（Contract）**：用 Pydantic 约束每步的输入/输出格式
4. **Checkpoint**：每步完成后存快照，支持查看审计轨迹
5. **审计 API**：`GET /api/v1/generate/{id}/audit` 返回完整执行记录

**预计工时**：5-7 天

**涉及文件变动**：

```
新建：
  sinan/harness/__init__.py
  sinan/harness/gates.py
  sinan/harness/validators/__init__.py
  sinan/harness/validators/browser_validator.py
  sinan/agents/fixer.py
  sinan/models/contracts.py
  sinan/api/routes/audit.py

修改：
  sinan/agents/state.py          ← 添加 gate_decision/iteration/max_iterations
  sinan/agents/graph.py          ← 加入门禁节点、Fixer 修复循环
  sinan/agents/__init__.py       ← 补充导出 FixerAgent
  sinan/services/generation_runner.py ← 传入 iteration 初始值，感知修复轮次
  sinan/api/app.py               ← 注册 audit_router
  requirements.txt               ← 添加 playwright
```

### 4.1 核心概念

Harness 工程的四个核心组件：

1. **Contract Validator（契约校验器）**：每步输入/输出用 Pydantic Schema 校验
2. **Gate Engine（门禁引擎）**：每步后判断 proceed / retry / fix / block
3. **Fixer Agent**：LLM 驱动的 HTML 修复，与 Gate 配合形成最多 3 轮的修复循环
4. **Checkpoint Store（检查点存储）**：每步完成后保存快照，支持审计和回滚

### Step 1：安装新依赖

**说明**：Phase 4 新增两个依赖：
- `langgraph-checkpoint-mysql`：LangGraph 官方的 MySQL Checkpoint 实现，用于在每个节点执行后自动持久化 state，支持断点续跑和审计。
- `playwright`：无头浏览器，用于渲染生成的 HTML 并检查 JS 报错、图表是否正确初始化。

在 `requirements.txt` 末尾追加：

```txt
langgraph-checkpoint-mysql>=0.1.0
playwright>=1.40.0
```

然后执行安装：

```bash
pip install langgraph-checkpoint-mysql playwright
playwright install chromium
```

---

### Step 2：新建契约模型文件

**说明**：Pydantic 契约模型用来约束每个 Agent 的输出格式。例如 Analyzer 必须输出某些关键字段，Coder 输出的 HTML 至少要有 100 个字符。这样一旦 LLM 输出偏轨，Pydantic 校验就会报错，触发重试而不是把垃圾数据传给下一步。

路径：`sinan/models/contracts.py`（新建文件）

```python
# sinan/models/contracts.py
from pydantic import BaseModel, Field, ValidationError
from typing import List


class AnalyzeContract(BaseModel):
    """Analyzer 输出契约：结构化需求描述必须包含这些核心字段。"""
    requirements: str = Field(..., min_length=20,
                              description="结构化需求清单，至少 20 个字符")

    def validate_content(self) -> List[str]:
        """业务内容校验，返回错误列表（空列表 = 通过）。"""
        errors = []
        # Pydantic 的 min_length 已保证长度，这里可追加更多业务规则
        # 例如：要求包含"功能"或"数据"等关键词（按需开启）
        return errors


class DesignContract(BaseModel):
    """Designer 输出契约：设计方案必须包含布局和配色描述。"""
    design: str = Field(..., min_length=20,
                        description="页面设计方案，至少 20 个字符")

    def validate_content(self) -> List[str]:
        """业务内容校验，返回错误列表（空列表 = 通过）。"""
        errors = []
        # 例如：要求包含布局或配色关键词（按需开启）
        return errors


class CodeContract(BaseModel):
    """Coder 输出契约：生成的 HTML 必须满足最低结构要求。"""
    html: str = Field(..., min_length=100, description="生成的 HTML，至少 100 字符")

    def validate_content(self) -> List[str]:
        """HTML 结构校验，返回错误列表（空列表 = 通过）。"""
        errors = []
        html_lower = self.html.lower()
        if "<!doctype" not in html_lower[:200]:
            errors.append("缺少 <!DOCTYPE html>")
        if "<html" not in html_lower:
            errors.append("缺少 <html> 标签")
        if "<body" not in html_lower:
            errors.append("缺少 <body> 标签")
        return errors


class VerifyContract(BaseModel):
    """Verifier 输出契约：校验结果必须明确给出通过/失败。"""
    verified: bool
    verify_message: str = Field(..., min_length=1)

    def validate_content(self) -> List[str]:
        return []
```

**设计说明**：每个契约类统一提供 `validate_content()` 方法，封装该步骤的业务校验规则，返回错误列表。门禁引擎（gates.py）调用这个方法，只负责根据结果做路由决策，不自己实现校验逻辑。两层职责完全分离：contract 负责"什么是合法输出"，gate 负责"不合法时怎么办"。

---

### Step 3：新建门禁引擎

**说明**：门禁节点在每个 Agent 执行完之后运行，根据 contract 的校验结果做路由决策。门禁有四种决策：
- `proceed`：通过，继续下一步
- `retry`：输出有问题，重新执行当前 Agent
- `fix`：代码层面有问题，进入 Fixer 修复
- `block`：超过最大修复次数，终止整个流程

**职责分工**：
- `contracts.py`（Step 2）负责"什么是合法输出"——用 Pydantic 做类型/格式校验，`validate_content()` 封装业务校验规则
- `gates.py`（本步）负责"不合法时怎么办"——调用 contract 拿到校验结果，只做路由决策

这样两层职责完全分离：扩展校验规则时只改 `contracts.py`，改路由策略时只改 `gates.py`。

首先创建 `sinan/harness/__init__.py`（空文件）：

```python
# sinan/harness/__init__.py
```

然后创建 `sinan/harness/gates.py`：

```python
# sinan/harness/gates.py
import logging
from dataclasses import dataclass, field
from typing import List
from pydantic import ValidationError

from sinan.models.contracts import AnalyzeContract, DesignContract, CodeContract

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    decision: str           # "proceed" | "retry" | "fix" | "block"
    reason: str = ""
    issues: List[str] = field(default_factory=list)


class GateEngine:
    """
    门禁引擎：在每个 Agent 步骤后评估输出质量，决定是继续/重试/修复/阻断。
    校验逻辑委托给各步骤的 Contract，门禁只做路由决策。
    """

    def evaluate(self, step: str, state: dict) -> GateResult:
        """根据步骤名调用对应的门禁方法。"""
        method = getattr(self, f"_gate_{step}", None)
        if method is None:
            logger.debug("no gate defined for step %s, proceeding", step)
            return GateResult(decision="proceed")
        return method(state)

    def _gate_analyze(self, state: dict) -> GateResult:
        try:
            contract = AnalyzeContract(requirements=state.get("requirements", ""))
        except ValidationError as e:
            issues = [err["msg"] for err in e.errors()]
            return GateResult(decision="retry", reason="需求分析格式校验失败", issues=issues)

        errors = contract.validate_content()
        if errors:
            return GateResult(decision="retry", reason="需求分析内容校验失败", issues=errors)
        return GateResult(decision="proceed")

    def _gate_design(self, state: dict) -> GateResult:
        try:
            contract = DesignContract(design=state.get("design", ""))
        except ValidationError as e:
            issues = [err["msg"] for err in e.errors()]
            return GateResult(decision="retry", reason="设计方案格式校验失败", issues=issues)

        errors = contract.validate_content()
        if errors:
            return GateResult(decision="retry", reason="设计方案内容校验失败", issues=errors)
        return GateResult(decision="proceed")

    def _gate_code(self, state: dict) -> GateResult:
        try:
            contract = CodeContract(html=state.get("html", ""))
        except ValidationError as e:
            issues = [err["msg"] for err in e.errors()]
            # ValidationError 说明连基本格式都不对，直接走 fix
            iteration = state.get("iteration", 0)
            if iteration >= state.get("max_iterations", 3):
                return GateResult(decision="block", reason="超过最大修复次数", issues=issues)
            return GateResult(decision="fix", reason="HTML 格式校验失败", issues=issues)

        errors = contract.validate_content()
        if errors:
            iteration = state.get("iteration", 0)
            if iteration >= state.get("max_iterations", 3):
                return GateResult(decision="block", reason="超过最大修复次数", issues=errors)
            return GateResult(decision="fix", reason="HTML 结构不合格", issues=errors)
        return GateResult(decision="proceed")

    def _gate_verify(self, state: dict) -> GateResult:
        if state.get("verified"):
            return GateResult(decision="proceed")
        iteration = state.get("iteration", 0)
        max_iter = state.get("max_iterations", 3)
        if iteration >= max_iter:
            return GateResult(
                decision="block",
                reason=f"验证失败且已达最大迭代次数 {max_iter}",
                issues=[state.get("verify_message", "未知错误")],
            )
        return GateResult(
            decision="retry",
            reason="验证未通过，进入修复循环",
            issues=[state.get("verify_message", "")],
        )
```

**`sinan/harness/state_machine.py`**（供调试和文档用，定义合法流转路径）：

```python
# sinan/harness/state_machine.py
from enum import Enum


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


TRANSITION_TABLE: dict[PipelineState, list[PipelineState]] = {
    PipelineState.INIT:       [PipelineState.ANALYSIS],
    PipelineState.ANALYSIS:   [PipelineState.DESIGN, PipelineState.FAILED],
    PipelineState.DESIGN:     [PipelineState.GENERATION, PipelineState.ANALYSIS],
    PipelineState.GENERATION: [PipelineState.VALIDATION],
    PipelineState.VALIDATION: [PipelineState.HOST, PipelineState.FIX, PipelineState.FAILED],
    PipelineState.FIX:        [PipelineState.GENERATION],
    PipelineState.HOST:       [PipelineState.COMPLETED, PipelineState.FAILED],
    PipelineState.COMPLETED:  [],
    PipelineState.FAILED:     [],
}


def can_transition(from_state: PipelineState, to_state: PipelineState) -> bool:
    return to_state in TRANSITION_TABLE.get(from_state, [])
```

---

### Step 4：新建 Fixer Agent

**说明**：Fixer 是 Phase 4 的核心新增节点。当 Verifier 发现 HTML 有问题时，Fixer 会拿着原始 HTML 和错误信息请 LLM 修复。每次执行都递增 `iteration`，`_gate_verify` 通过读 `iteration` 决定继续修复还是 block。温度用 0.2 让修复更保守，减少引入新问题的风险。

新建 `sinan/agents/fixer.py`：

```python
# sinan/agents/fixer.py
import logging
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个前端代码修复专家。
你会收到一段有问题的 HTML 页面代码，以及具体的错误描述。
请修复这些问题，返回完整的、可直接在浏览器运行的 HTML 页面。

要求：
1. 只修复错误描述中提到的问题，不要大改其他内容
2. 返回完整的 HTML 文档（包含 <!DOCTYPE html>、<head>、<body>）
3. 只返回纯 HTML 代码，不要任何 markdown 格式（不要 ```html 包裹）
4. 不要任何解释文字，直接输出修复后的 HTML"""


class FixerAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def run(self, state: PageGenState) -> dict:
        iteration = state.get("iteration", 0) + 1
        logger.info("fixer running, iteration=%d", iteration)

        user_content = (
            f"错误描述：\n{state.get('verify_message', '未知错误')}\n\n"
            f"需要修复的 HTML：\n{state.get('html', '')}"
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        fixed_html = await self.llm.chat(messages, temperature=0.2)
        fixed_html = self._strip_markdown(fixed_html)

        return {
            "html": fixed_html,
            "iteration": iteration,
            # 重置验证状态，让 verify 节点重新校验修复后的 HTML
            "verified": False,
            "verify_message": "",
        }

    def _strip_markdown(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```html"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()
```

---

### Step 5：更新 PageGenState，加入 Harness 控制字段

**说明**：Phase 4 新增三个字段：
- `iteration`：当前修复轮次（从 0 开始）
- `max_iterations`：最大允许修复轮次（默认 3）
- `gate_decision`：当前门禁节点的决策结果（`proceed` / `retry` / `fix` / `block`）

修改 `sinan/agents/state.py`：

```python
# sinan/agents/state.py
from typing import TypedDict


class PageGenState(TypedDict):
    """LangGraph 节点之间共享的流水线状态。"""

    # 输入
    prompt: str

    # Analyzer 产出
    requirements: str       # 结构化需求：功能列表、交互要点

    # Designer 产出
    design: str             # 设计方案：布局结构、配色方案、组件清单

    # Coder 产出
    html: str               # 生成的 HTML 页面

    # Verifier 产出
    verified: bool          # 是否通过验证
    verify_message: str     # 验证结论或错误描述

    # Phase 4 新增：Harness 控制字段
    iteration: int          # 当前修复迭代次数（从 0 开始）
    max_iterations: int     # 最大允许修复次数（默认 3）
    gate_decision: str      # 当前门禁决策（proceed/retry/fix/block）
```

---

### Step 6：改造 graph.py，接入 Fixer + 门禁

**说明**：这是 Phase 4 最核心的改动。在每个 Agent 节点之后插入对应的 `gate_xxx` 节点，由门禁决策路由后续走向：

```
analyze → gate_analyze → (proceed: design | retry: analyze)
design  → gate_design  → (proceed: code   | retry: design)
code    → gate_code    → (proceed: verify | fix: fix | block: END)
verify  → gate_verify  → (proceed: END    | retry: fix | block: END)
fix     → code（重新生成，进入修复循环）
```

同时，把 Phase 3 里那个占位 lambda `"end" if state["verified"] else "end"` 真正改掉，接入真实路由。用 `MemorySaver` 作为开发阶段的 Checkpoint（不需要额外配置），生产环境换 `AsyncMySqlSaver` 时只改一行。

修改 `sinan/agents/graph.py`（完整替换）：

```python
# sinan/agents/graph.py
import logging
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from sinan.agents.state import PageGenState
from sinan.agents.analyzer import AnalyzerAgent
from sinan.agents.designer import DesignerAgent
from sinan.agents.coder import CoderAgent
from sinan.agents.verifier import VerifierAgent
from sinan.agents.fixer import FixerAgent
from sinan.agents.llm import LLMClient
from sinan.harness.gates import GateEngine

logger = logging.getLogger(__name__)


def build_graph(llm: LLMClient) -> StateGraph:
    analyzer = AnalyzerAgent(llm)
    designer = DesignerAgent(llm)
    coder = CoderAgent(llm)
    verifier = VerifierAgent()
    fixer = FixerAgent(llm)
    gate_engine = GateEngine()

    # 门禁节点（不调用 LLM，只做决策）
    async def gate_analyze(state: PageGenState) -> dict:
        result = gate_engine.evaluate("analyze", state)
        logger.info("gate_analyze: decision=%s", result.decision)
        return {"gate_decision": result.decision}

    async def gate_design(state: PageGenState) -> dict:
        result = gate_engine.evaluate("design", state)
        logger.info("gate_design: decision=%s", result.decision)
        return {"gate_decision": result.decision}

    async def gate_code(state: PageGenState) -> dict:
        result = gate_engine.evaluate("code", state)
        logger.info("gate_code: decision=%s, issues=%s", result.decision, result.issues)
        return {"gate_decision": result.decision}

    async def gate_verify(state: PageGenState) -> dict:
        result = gate_engine.evaluate("verify", state)
        logger.info("gate_verify: decision=%s", result.decision)
        return {"gate_decision": result.decision}

    # 构建图
    graph = StateGraph(PageGenState)

    # 注册节点
    graph.add_node("analyze", analyzer.run)
    graph.add_node("gate_analyze", gate_analyze)
    graph.add_node("design", designer.run)
    graph.add_node("gate_design", gate_design)
    graph.add_node("code", coder.run)
    graph.add_node("gate_code", gate_code)
    graph.add_node("verify", verifier.run)
    graph.add_node("gate_verify", gate_verify)
    graph.add_node("fix", fixer.run)

    # 连边：业务节点 → 门禁节点
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "gate_analyze")
    graph.add_conditional_edges(
        "gate_analyze",
        lambda s: s.get("gate_decision", "proceed"),
        {"proceed": "design", "retry": "analyze"},
    )
    graph.add_edge("design", "gate_design")
    graph.add_conditional_edges(
        "gate_design",
        lambda s: s.get("gate_decision", "proceed"),
        {"proceed": "code", "retry": "design"},
    )
    graph.add_edge("code", "gate_code")
    graph.add_conditional_edges(
        "gate_code",
        lambda s: s.get("gate_decision", "proceed"),
        {"proceed": "verify", "fix": "fix", "block": END},
    )
    graph.add_edge("verify", "gate_verify")
    graph.add_conditional_edges(
        "gate_verify",
        lambda s: s.get("gate_decision", "proceed"),
        {"proceed": END, "retry": "fix", "block": END},
    )

    # fix 之后重新走 code（修复后重新验证）
    graph.add_edge("fix", "code")

    # Checkpoint：开发阶段用内存版，生产换 AsyncMySqlSaver 时只改这一行
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
```

**说明**：`gate_decision` 用 `.get("gate_decision", "proceed")` 而不是直接用 `[]`，是因为第一次调用时 state 里还没有这个 key，用 `.get` 默认 proceed 可以避免 KeyError。

---

### Step 7：更新 GenerationRunner，感知修复迭代

**说明**：Runner 需要在初始 state 里传入 `iteration=0` 和 `max_iterations=3`，让 Fixer 和 Gate 能读到这两个控制参数。同时加入 `config={"configurable": {"thread_id": session_id}}` 参数——LangGraph checkpointer 要求每次 invoke 时指定 thread_id，以便按 session 隔离状态，不同 session 的 checkpoint 不会互相影响。如果经历了修复轮次，也要推送 fix 事件让前端感知到。

修改 `sinan/services/generation_runner.py`（完整替换）：

```python
# sinan/services/generation_runner.py
import logging

from sinan.agents.llm import LLMClient
from sinan.agents.graph import build_graph
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep, PageVersion
from sinan.models.enums import SessionStatus, PageStatus
from sinan.services.session_store import session_store
from sinan.services.generation_event_bus import event_bus
from sinan.config.settings import settings

logger = logging.getLogger(__name__)


class GenerationRunner:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.graph = build_graph(llm)

    async def start(self, session_id: str) -> None:
        """后台异步执行生成流程，不阻塞请求。"""
        await session_store.update(session_id, status=SessionStatus.RUNNING)

        try:
            session = await session_store.get(session_id)
            prompt = session.prompt if session else ""

            # 推送各步骤开始事件（在 graph.ainvoke 之前，让前端看到进度）
            await event_bus.publish(session_id, "analyze", {"message": "正在分析需求..."})
            await self._write_step(session_id, "analyze", "开始需求分析")

            await event_bus.publish(session_id, "design", {"message": "正在制定设计方案..."})
            await self._write_step(session_id, "design", "开始设计")

            await event_bus.publish(session_id, "code", {"message": "AI 正在生成页面代码..."})
            await self._write_step(session_id, "code", "开始生成")

            # 执行 LangGraph 图
            # Phase 4 新增：传入 iteration 和 max_iterations 初始值
            # config thread_id 让 checkpointer 按 session 隔离状态
            final_state = await self.graph.ainvoke(
                {
                    "prompt": prompt,
                    "iteration": 0,
                    "max_iterations": 3,
                },
                config={"configurable": {"thread_id": session_id}},
            )

            # 如果经历了修复，推送修复事件
            if final_state.get("iteration", 0) > 0:
                await event_bus.publish(
                    session_id,
                    "fix",
                    {"message": f"经过 {final_state['iteration']} 轮修复"},
                )
                await self._write_step(
                    session_id, "fix",
                    f"修复完成，共 {final_state['iteration']} 轮",
                )

            # 推送验证结果
            await self._write_step(session_id, "verify", final_state.get("verify_message", ""))
            await event_bus.publish(
                session_id, "verify",
                {"message": final_state.get("verify_message", "校验完成")},
            )

            if not final_state.get("verified"):
                raise ValueError(
                    f"验证失败（已修复 {final_state.get('iteration', 0)} 轮）："
                    f"{final_state.get('verify_message', '未知错误')}"
                )

            html = final_state["html"]

        except Exception as e:
            logger.exception("generation failed for session %s", session_id)
            await event_bus.publish(session_id, "error", {"message": f"生成失败：{e}"})
            await session_store.update(session_id, status=SessionStatus.FAILED)
            await event_bus.publish_done(session_id)
            return

        # 存页面、更新 session
        marker = f"page_{session_id[:8]}"
        version = 1
        await self._save_page(marker, version, html, created_by=session_id)
        await session_store.update(
            session_id,
            status=SessionStatus.COMPLETED,
            marker=marker,
            version=version,
            preview_url=f"/api/v1/page/{marker}",
        )
        await event_bus.publish(
            session_id,
            "host",
            {
                "message": f"页面已生成，预览地址: /api/v1/page/{marker}",
                "url": f"/api/v1/page/{marker}",
            },
        )
        await event_bus.publish_done(session_id)

    async def _write_step(self, session_id: str, step: str, message: str) -> None:
        record = GenSessionStep(
            session_id=session_id,
            step=step,
            direction="output",
            output_data={"message": message},
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()

    async def _save_page(self, marker: str, version: int, html: str, created_by: str) -> None:
        record = PageVersion(
            marker=marker,
            version=version,
            html_content=html,
            status=PageStatus.PUBLISHED,
            created_by=created_by,
        )
        async with AsyncSessionLocal() as db:
            db.add(record)
            await db.commit()


_llm = LLMClient(
    api_key=settings.llm_api_key,
    model=settings.llm_model,
    base_url=settings.llm_base_url,
)
generation_runner = GenerationRunner(_llm)
```

---

### Step 8：新建浏览器验证器（可选）

**说明**：`BrowserValidator` 在无头 Chromium 里加载 HTML，检查 JS 错误和图表渲染状态。`playwright` 未安装时直接跳过（返回 passed=True），不会阻塞主流程。`wait_for_timeout(2000)` 给 ECharts 等 JS 渲染留出时间。

先创建 `sinan/harness/validators/__init__.py`（空文件），再创建 `sinan/harness/validators/browser_validator.py`：

```python
# sinan/harness/validators/browser_validator.py
import logging

logger = logging.getLogger(__name__)


class BrowserValidator:
    """
    用 Playwright 在无头 Chromium 里加载 HTML，检查 JS 错误和渲染状态。
    需要先安装：pip install playwright && playwright install chromium
    playwright 未安装时自动降级为跳过（返回 passed=True）。
    """

    async def validate(self, html: str) -> dict:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("playwright 未安装，跳过浏览器验证")
            return {"passed": True, "issues": [], "chart_count": 0}

        issues = []
        chart_count = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            # 收集 JS 错误
            js_errors = []
            page.on("pageerror", lambda err: js_errors.append(str(err)))
            try:
                await page.set_content(html, timeout=15000)
                await page.wait_for_timeout(2000)  # 等待 JS 执行

                # 检查 ECharts 渲染
                charts = await page.query_selector_all("[_echarts_instance_]")
                chart_count = len(charts)
                if chart_count == 0 and "echarts" in html.lower():
                    issues.append("ECharts 未正确初始化（引用了 ECharts 但未找到渲染实例）")

                # 检查页面内容不为空
                body_text = await page.inner_text("body")
                if len(body_text.strip()) < 10:
                    issues.append("页面 body 内容为空")

                # 附上 JS 错误
                issues.extend([f"JS Error: {e}" for e in js_errors])

            finally:
                await browser.close()

        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "chart_count": chart_count,
        }
```

---

### Step 9：新建审计 API

**说明**：审计 API 返回某次生成的完整执行轨迹——每个步骤执行了什么、时间戳、门禁决策。对调试 LLM 输出质量和排查修复失败原因非常有用。

新建 `sinan/api/routes/audit.py`：

```python
# sinan/api/routes/audit.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sinan.models.database import AsyncSessionLocal
from sinan.models.tables import GenSessionStep, GenSession

router = APIRouter()


@router.get("/generate/{session_id}/audit")
async def get_audit(session_id: str):
    """
    返回指定会话的完整执行审计轨迹。
    包含每个步骤的输入/输出、门禁决策、时间戳。
    """
    async with AsyncSessionLocal() as db:
        # 先确认 session 存在
        session_result = await db.execute(
            select(GenSession).where(GenSession.id == session_id)
        )
        session = session_result.scalar_one_or_none()
        if session is None:
            return JSONResponse(status_code=404, content={"detail": f"会话 {session_id} 不存在"})

        # 查询所有步骤记录
        steps_result = await db.execute(
            select(GenSessionStep)
            .where(GenSessionStep.session_id == session_id)
            .order_by(GenSessionStep.created_at)
        )
        steps = steps_result.scalars().all()

    audit_trail = [
        {
            "step": s.step,
            "direction": s.direction,
            "output": s.output_data,
            "gate_decision": s.gate_decision,
            "timestamp": s.created_at.isoformat() if s.created_at else None,
        }
        for s in steps
    ]

    return {
        "session_id": session_id,
        "status": session.status.value if session.status else None,
        "prompt": session.prompt,
        "total_steps": len(steps),
        "audit_trail": audit_trail,
    }
```

然后修改 `sinan/api/app.py`，注册 audit_router（只改 import 和 include_router）：

```python
# sinan/api/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sinan.config.settings import settings
from sinan.core.logging import setup_logging
from sinan.models.database import init_db
from sinan.api.routes.health import router as health_router
from sinan.api.routes.generate import router as generate_router
from sinan.api.routes.preview import router as preview_router
from sinan.api.routes.audit import router as audit_router   # ← 新增


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.debug)
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(generate_router, prefix="/api/v1")
    app.include_router(preview_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")       # ← 新增
    return app


app = create_app()
```

---

### Step 10：更新 agents `__init__.py`

修改 `sinan/agents/__init__.py`，补充 FixerAgent 的导出：

```python
# sinan/agents/__init__.py
from sinan.agents.llm import LLMClient
from sinan.agents.state import PageGenState
from sinan.agents.analyzer import AnalyzerAgent
from sinan.agents.designer import DesignerAgent
from sinan.agents.coder import CoderAgent
from sinan.agents.verifier import VerifierAgent
from sinan.agents.fixer import FixerAgent       # ← 新增
from sinan.agents.graph import build_graph
```

---

### Step 11：验收测试

**11.1 启动服务**

```bash
python -m sinan
```

**11.2 触发正常流程（验证全链路通过）**

```bash
# 发起生成
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "做一个 GPU 使用率监控看板，展示 8 张卡的实时使用率折线图"}'

# 拿到 session_id，订阅 SSE（把 xxx 换掉）
curl -N http://localhost:8000/api/v1/generate/xxx/stream
```

正常情况下 SSE 顺序：

```
event: analyze    正在分析需求...
event: design     正在制定设计方案...
event: code       AI 正在生成页面代码...
event: verify     校验通过
event: host       页面已生成，预览地址: /api/v1/page/page_xxx
event: done
```

如果触发了修复：

```
event: analyze
event: design
event: code
event: fix        经过 1 轮修复
event: verify     校验通过
event: host
event: done
```

**11.3 查看审计轨迹**

```bash
curl http://localhost:8000/api/v1/generate/xxx/audit
```

预期返回：

```json
{
  "session_id": "xxx",
  "status": "completed",
  "prompt": "做一个 GPU 使用率监控看板...",
  "total_steps": 5,
  "audit_trail": [
    {"step": "analyze", "direction": "output", "output": {"message": "开始需求分析"}, "gate_decision": null, "timestamp": "..."},
    {"step": "design", ...},
    {"step": "code", ...},
    {"step": "verify", ...},
    {"step": "host", ...}
  ]
}
```

---

### 文件变更汇总

| 操作 | 文件 |
|------|------|
| 修改 | `requirements.txt`（加 langgraph-checkpoint-mysql、playwright） |
| 新建 | `sinan/models/contracts.py` |
| 新建 | `sinan/harness/__init__.py` |
| 新建 | `sinan/harness/gates.py` |
| 新建 | `sinan/harness/state_machine.py` |
| 新建 | `sinan/harness/validators/__init__.py` |
| 新建 | `sinan/harness/validators/browser_validator.py` |
| 新建 | `sinan/agents/fixer.py` |
| 修改 | `sinan/agents/state.py`（加 iteration/max_iterations/gate_decision） |
| 修改 | `sinan/agents/graph.py`（接入门禁节点 + Fixer 循环 + MemorySaver） |
| 修改 | `sinan/services/generation_runner.py`（传入 iteration 初始值，感知修复轮次） |
| 新建 | `sinan/api/routes/audit.py` |
| 修改 | `sinan/api/app.py`（注册 audit_router） |
| 修改 | `sinan/agents/__init__.py`（导出 FixerAgent） |

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
