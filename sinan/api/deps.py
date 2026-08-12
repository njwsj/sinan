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