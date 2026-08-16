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
    db_name: str = "sinan"

    # --- Redis（保留旧字段）---
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    # --- LLM ---
    llm_api_key: str = ""
    llm_model: str = "glm-4"
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # --- Storage ---
    storage_type: str = "local"
    storage_local_path: str = "./output/pages"
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