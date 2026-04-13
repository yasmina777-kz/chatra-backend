import os
import tempfile
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from deps import get_current_user
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.file_service import read_file
from services.storage import YC_ENABLED, upload_bytes

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "txt", "md", "csv", "rtf",
    "png", "jpg", "jpeg", "gif", "webp",
    "zip", "rar", "sm",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# MIME types for common extensions (used when uploading to YC)
_MIME = {
    "pdf": "application/pdf",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "gif": "image/gif", "webp": "image/webp",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain", "md": "text/markdown", "csv": "text/csv",
}


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
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

    # ── Parse file content (requires a local path) ────────────────────────────
    parsed = {}
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        parsed = read_file(tmp_path)
    except Exception:
        pass  # parsing is best-effort, don't fail the upload
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ── Store file ────────────────────────────────────────────────────────────
    if YC_ENABLED:
        try:
            key = f"uploads/{unique_filename}"
            content_type = _MIME.get(ext, "application/octet-stream")
            file_url = upload_bytes(content, key, content_type)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Object storage upload failed: {e}")
    else:
        # Fallback: save locally
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        try:
            with open(file_path, "wb") as buf:
                buf.write(content)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")
        file_url = f"{APP_BASE_URL.rstrip('/')}/uploads/{unique_filename}"

    return JSONResponse(content={"file_url": file_url, "filename": file.filename, "parsed": parsed})