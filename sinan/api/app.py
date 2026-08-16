from contextlib import asynccontextmanager
from fastapi import FastAPI
from sinan.config.settings import settings
from sinan.core.logging import setup_logging
from sinan.models.database import init_db
from sinan.api.routes.health import (
    legacy_router as legacy_health_router,
    router as health_router,
)
from sinan.api.routes.generate import (
    legacy_router as legacy_generate_router,
    router as generate_router,
)
from sinan.api.routes.preview import (
    router as preview_router,
    page_router as preview_page_router,
)
from sinan.api.routes.session import router as session_router
from sinan.api.routes.pages import router as pages_router
from sinan.api.routes.upload import router as upload_router
from sinan.api.routes.audit import router as audit_router
from sinan.api.routes import data as data_routes

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服务器启动时：初始化日志和数据库
    setup_logging(settings.debug)
    await init_db()
    yield
    # 服务器关闭时：在此处添加清理逻辑

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    # 参考项目主路径（各 router 自带 /api/page 前缀）
    app.include_router(health_router)
    app.include_router(generate_router)
    app.include_router(session_router)
    app.include_router(pages_router)
    app.include_router(preview_page_router)
    app.include_router(upload_router)

    # 旧接口，过渡期保留
    app.include_router(legacy_health_router)
    app.include_router(legacy_generate_router)

    # 尚未完成路径适配的现有接口
    app.include_router(preview_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(data_routes.router, prefix="/api/v1")
    return app

# 全局 app 实例，供 uvicorn 加载：uvicorn.run("sinan.api.app:app")
app = create_app()