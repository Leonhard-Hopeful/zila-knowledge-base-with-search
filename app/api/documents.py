import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.config import settings
from app.core import vectorstore
from app.core.status import get_status, reset_status, set_status
from app.security import require_api_key
from app.worker.tasks import ingest_document

router = APIRouter(prefix="/v1/documents", dependencies=[Depends(require_api_key)])
ALLOWED = {".pdf", ".docx", ".pptx", ".md", ".markdown", ".txt"}


@router.post("", status_code=202)
async def upload(
    file: UploadFile = File(...),
    department: str = Form(...),
    cohort_id: str = Form(...),
    title: str | None = Form(None),
    chunk_size: int | None = Form(None, ge=100, le=1500),
    chunk_overlap: int | None = Form(None, ge=0, le=300),
    document_id: str | None = Form(None),   # pass an existing ID to replace a doc
):
    department = department.lower().strip()
    if department not in settings.allowed_departments:
        raise HTTPException(400, f"Unknown department: {department}")

    filename = Path(file.filename or "upload").name     # strip any path components
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, f"Unsupported type {ext}")

    if chunk_size is not None and chunk_overlap is not None and chunk_overlap >= chunk_size:
        raise HTTPException(422, "chunk_overlap must be smaller than chunk_size")

    doc_id = document_id or str(uuid.uuid4())
    dest_dir = Path(settings.upload_dir) / doc_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    if dest.stat().st_size > settings.max_upload_mb * 1024 * 1024:
        dest.unlink()
        raise HTTPException(413, "File too large")

    reset_status(doc_id)
    set_status(doc_id, state="queued", department=department,
               cohort_id=cohort_id, filename=filename)
    ingest_document.delay(doc_id, str(dest), department, cohort_id,
                          title or filename, filename, chunk_size, chunk_overlap)
    return {"document_id": doc_id, "status": "queued"}


@router.get("/{doc_id}")
def status(doc_id: str):
    s = get_status(doc_id)
    if not s:
        raise HTTPException(404, "Not found")
    return {"document_id": doc_id, **s}


@router.delete("/{doc_id}")
def delete(doc_id: str):
    vectorstore.delete_document(doc_id)
    shutil.rmtree(Path(settings.upload_dir) / doc_id, ignore_errors=True)
    return {"deleted": doc_id}
