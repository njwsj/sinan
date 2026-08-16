# sinan/api/routes/data.py
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException
from sinan.services.data_service import data_service
from sinan.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/data/upload")
async def upload_data_file(file: UploadFile = File(...)):
    """
    上传 Excel 文件，解析后把完整数据存到本地文件，返回轻量元数据供前端使用。

    前端拿到响应后，把 file_id / filename / columns 存起来，
    发起 /generate 请求时放入 attachments 列表传回。

    返回格式：
    {
      "file_id": "abc123",
      "filename": "sales.xlsx",
      "columns": ["月份", "销售额", "利润"],
      "row_count": 100,
      "preview": [前5行数据, ...]
    }
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="只支持 .xlsx / .xls 格式")

    file_data = await file.read()
    if len(file_data) > 10 * 1024 * 1024:  # 10MB 限制
        raise HTTPException(status_code=413, detail="文件超过 10MB 限制")

    try:
        meta = await data_service.parse_and_store(
            file_data=file_data,
            storage_dir=settings.attachment_storage_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"filename": file.filename, **meta}
