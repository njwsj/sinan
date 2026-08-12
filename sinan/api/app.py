from contextlib import asynccontextmanager
from fastapi import FastAPI
from sinan.config.settings import settings
from sinan.core.logging import setup_logging
from sinan.models.database import init_db
from sinan.api.routes.health import router as health_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服务器启动时：初始化日志和数据库
    setup_logging(settings.debug)
    await init_db()
    yield
    # 服务器关闭时：在此处添加清理逻辑

def create_app() -> FastAPI:
    # 创建 FastAPI 实例并注册路由
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    return app

# 全局 app 实例，供 uvicorn 加载：uvicorn.run("sinan.api.app:app")
app = create_app()