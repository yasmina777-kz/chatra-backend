import os
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from deps import get_current_user
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.file_service import read_file

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "txt", "md", "csv", "rtf",
    "png", "jpg", "jpeg", "gif", "webp",
    "zip", "rar","sm",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),  # require auth
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"File type '.{ext}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50 MB)")

    unique_filename = f"{uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            buffer.write(content)

    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
    parsed = read_file(file_path)

    file_url = f"{APP_BASE_URL.rstrip('/')}/uploads/{unique_filename}"
    return JSONResponse(content={"file_url": file_url, "filename": file.filename,"parsed": parsed})
