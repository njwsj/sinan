from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from sinan.api.context import new_trace_id, request_user_var, trace_id_var
import time
import logging
from sinan.core.exceptions import SinanError
from fastapi.responses import FileResponse, JSONResponse

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
    from sinan.services.generation_supervisor import start_supervisor, stop_supervisor
    await start_supervisor()
    yield
    # 服务器关闭时：在此处添加清理逻辑
    """
    日志 → 数据库 → supervisor 启动；
    关闭时先停 supervisor（取消本地 run_job，未完成 Job 靠租约过期在下次启动恢复），
    再关 Redis，最后框架关数据库。Redis 懒加载，首次取消才建连。
    """
    await stop_supervisor()
    from sinan.services.redis import close_redis
    await close_redis()

def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.middleware("http")
    async def trace_and_access_log(request: Request, call_next):
        """为每个请求注入 trace_id 并记录访问日志。"""
        trace_id_var.set(new_trace_id())
        start = time.time()
        response = await call_next(request)
        elapsed = int((time.time() - start) * 1000)
        user = request_user_var.get()
        logging.getLogger("sinan.access").info(
            "%s\t%s\t%dms\t%s\t%s\t%d\t%s",
            time.strftime("%Y-%m-%d %H:%M:%S"),
            request.method,
            elapsed,
            request.url.path,
            str(request.query_params) if request.query_params else "",
            response.status_code,
            user,
        )
        return response

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

    # 本地调试页：可视化 SSE 事件流（同源，避免 CORS）
    _DEBUG_PAGE = Path(__file__).resolve().parent.parent / "static" / "debug.html"

    @app.get("/debug", include_in_schema=False)
    async def debug_console():
        return FileResponse(_DEBUG_PAGE, media_type="text/html")

    """全局异常处理器 - 捕获 SinanError 并返回 JSONResponse"""

    @app.exception_handler(SinanError)
    async def sinan_error_handler(request: Request, exc: SinanError):
        # 与参考一致：响应体只含 error 字段，状态码用 exc.code
        return JSONResponse(status_code=exc.code, content={"error": exc.message})

    return app

# 全局 app 实例，供 uvicorn 加载：uvicorn.run("sinan.api.app:app")
app = create_app()