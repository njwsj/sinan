from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "sinan"
    debug: bool = True
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "sinan"
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    llm_api_key: str = ""
    llm_model: str = "glm-4"
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    storage_type: str = "local"
    storage_local_path: str = "./output/pages"

    class Config:
        env_file = ".env"

settings = Settings()