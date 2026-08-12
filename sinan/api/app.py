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
    # 服务器启动时：初始化日志和数据库
    setup_logging(settings.debug)
    await init_db()
    yield
    # 服务器关闭时：在此处添加清理逻辑

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)                          # /health（无前缀）
    app.include_router(generate_router, prefix="/api/v1")     # /api/v1/generate
    app.include_router(preview_router, prefix="/api/v1")      # /api/v1/page/{marker}
    return app

# 全局 app 实例，供 uvicorn 加载：uvicorn.run("sinan.api.app:app")
app = create_app()