from fastapi import APIRouter


router = APIRouter(prefix="/api/page", tags=["health"])
legacy_router = APIRouter(tags=["legacy"], include_in_schema=False)


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    return {"status": "ready"}


@legacy_router.get("/health")
async def legacy_health():
    return {"status": "ok"}