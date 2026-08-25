from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # --- App ---
    app_name: str = "sinan"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Database（保留旧字段，database.py 仍在用）---
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "sinan_v2"

    # --- Redis（保留旧字段）---
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 1
    redis_max_connections: int = 64


    # --- SSE / 事件总线 ---
    event_bus_backend: str = "redis"      # redis / memory（memory 仅本地开发）
    sse_max_events: int = 1000            # 每个 session 保留的事件条数上限
    sse_terminal_ttl_seconds: int = 120   # 终止事件后 key 的存活时间
    sse_poll_seconds: float = 1.0         # subscribe 轮询间隔
    sse_ping_seconds: int = 30            # SSE 心跳间隔

    # --- LLM ---
    llm_api_key: str = ""
    llm_model: str = "glm-4"
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # --- Storage ---
    storage_type: str = "local"
    storage_local_path: str = "./output/pages"
    storage_base_path: str = "./output/storage"
    attachment_storage_path: str = "/tmp/sinan_attachments"

    # --- BOS ---
    bos_endpoint: str = ""
    bos_bucket: str = ""

    # --- Auth ---
    auth_mode: str = "none"  # none / dev / uuap，Step 3 使用

    # --- Runtime ---
    opencode_enabled: bool = False
    opencode_base_url: str = ""
    opencode_mode: str = "opencode"

    # --- Feature / Job ---
    max_generation_attempts: int = 3
    job_lease_seconds: int = 60
    event_retention_seconds: int = 3600

    # --- Pipeline / Harness（Step 7）---
    auto_confirm_threshold: float = 0.3   # 参考 page/config/dev.config:42
    max_fix_rounds: int = 3               # 参考 page/config/settings.py:63
    quality_threshold: float = 0.8        # 参考 page/harness/gates.py:113 硬编码值
    render_validation_enabled: bool = False   # Step 15 对照前必须置 True
    render_validation_timeout: int = 20
    # --- Skill / 知识库 / 数据源（Step 12）---
    # 差异说明：参考从 BOS 下载 zip 安装（settings.claude_code_skills_path 只是解压目标），
    # sinan 不出网，Skill 包直接以目录形式放在 skills_dir 下，install 只做扫描 + 落库。
    # skills_dir / knowledge_dir 的相对路径按**项目根**解析（见 skill_package._PROJECT_ROOT
    # 与 knowledge_context._PROJECT_ROOT），不按 Path.cwd()，避免换工作目录启动就找不到包。
    skills_dir: str = "./sinan/skills"             # 本地 Skill 包根目录
    skill_sync_on_startup: bool = True            # 启动时把本地包 upsert 进 skill_definition
    skill_timeout_seconds: int = 60               # 单个 Skill 子进程超时（参考默认 60s）
    skill_output_limit: int = 20000               # 注入 state 前的输出截断上限
    skill_sse_preview_limit: int = 2000           # skill_result 事件里 content 的截断上限（对齐参考）
    skill_route_by_llm: bool = False              # False 只用关键词路由，不额外花 LLM 调用
    skill_max_concurrent: int = 1                 # 同一次生成里串行执行 Skill，便于事件顺序对照

    knowledge_dir: str = "./knowledge"            # 本地知识库根目录（相对路径与 file:// 都在此下解析）
    knowledge_allow_http: bool = False            # 学习项目默认不出网；开启后仍做 SSRF 校验
    knowledge_fetch_timeout: int = 20
    knowledge_max_chars: int = 50000              # 单篇知识清洗后的字符上限（对齐参考 50000）
    knowledge_total_max_chars: int = 120000       # 所有知识合并后注入 prompt 的总上限

    datasource_timeout_seconds: int = 10          # api 类数据源单次请求超时
    datasource_error_policy: str = "ignore"       # ignore / fail：默认失败不阻断流水线

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    class Config:
        env_file = ".env"

settings = Settings()