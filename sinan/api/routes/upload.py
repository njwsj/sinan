# sinan/api/routes/upload.py
"""Upload 资源路由（Step 1 桩实现，真实上传逻辑待 Step 9 适配）。

参考位置 page/api/routes/upload.py:134
现有真实实现在 /api/v1/data/upload（data.py），Step 9 再对齐到此路径。
认证：Step 1 暂不校验，待 Step 3。
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/page", tags=["upload"])


@router.post("/upload")
async def upload():
    """占位端点（桩：待 Step 9 接入附件解析与 Artifact 存储）。"""
    return JSONResponse(
        status_code=501,
        content={"detail": "upload not implemented yet", "_stub": "pending Step 9"},
    )