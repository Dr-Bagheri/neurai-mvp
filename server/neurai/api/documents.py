"""Document upload + indexing for RAG (owner-scoped)."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from neurai.auth.deps import CurrentUser, current_user
from neurai.config import get_config
from neurai.db import get_db
from neurai.jobs import get_job_queue

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_SUFFIXES = {".pdf", ".txt", ".md"}
MAX_SIZE_BYTES = 50 * 1024 * 1024


@router.get("")
def list_documents(user: CurrentUser = Depends(current_user)):
    rows = get_db().query(
        "SELECT id, filename, mime, status, created_at FROM documents "
        "WHERE owner_id=? ORDER BY id DESC",
        (user.id,),
    )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def upload_document(file: UploadFile, user: CurrentUser = Depends(current_user)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, f"فرمت پشتیبانی نمی‌شود ({', '.join(sorted(ALLOWED_SUFFIXES))})")
    data = await file.read()
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(413, "حجم فایل بیش از حد مجاز است")

    cfg = get_config()
    user_dir = cfg.documents_dir / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-؀-ۿ]", "_", Path(file.filename or "file").name)
    path = user_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    path.write_bytes(data)

    doc_id = get_db().insert(
        "INSERT INTO documents(owner_id, filename, path, mime) VALUES(?,?,?,?)",
        (user.id, safe_name, str(path), file.content_type or ""),
    )
    get_job_queue().enqueue("index_document", {"document_id": doc_id}, priority=6)
    return {"id": doc_id, "filename": safe_name, "status": "uploaded"}


@router.delete("/{doc_id}")
def delete_document(doc_id: int, user: CurrentUser = Depends(current_user)):
    db = get_db()
    doc = db.query_one("SELECT * FROM documents WHERE id=? AND owner_id=?", (doc_id, user.id))
    if doc is None:
        raise HTTPException(404, "سند پیدا نشد")
    db.execute("DELETE FROM rag_chunks WHERE owner_id=? AND kind='document' AND ref_id=?",
               (user.id, doc_id))
    db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    try:
        Path(doc["path"]).unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}
