"""Index jobs: transcripts and uploaded documents → rag_chunks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neurai.db import get_db

from .store import index_text


def transcript_text(meeting_id: int, preferred_pass: str = "quality") -> str:
    """Assemble transcript text; falls back to the live pass if the quality
    pass hasn't run yet."""
    db = get_db()
    for pass_name in (preferred_pass, "live"):
        rows = db.query(
            "SELECT speaker_label, text FROM transcript_segments "
            "WHERE meeting_id=? AND pass=? ORDER BY start_ms",
            (meeting_id, pass_name),
        )
        if rows:
            names = {
                r["label"]: r["display_name"]
                for r in db.query("SELECT label, display_name FROM speaker_names WHERE meeting_id=?", (meeting_id,))
            }
            lines = []
            for r in rows:
                label = r["speaker_label"]
                speaker = names.get(label, label) if label else None
                lines.append(f"{speaker}: {r['text']}" if speaker else r["text"])
            return "\n".join(lines)
    return ""


async def index_transcript_job(payload: dict[str, Any]) -> None:
    meeting_id = int(payload["meeting_id"])
    db = get_db()
    meeting = db.query_one("SELECT owner_id, sensitivity FROM meetings WHERE id=?", (meeting_id,))
    if meeting is None:
        return
    if meeting["sensitivity"] == "confidential":
        # D4: «محرمانه» meetings stay out of cross-meeting search entirely.
        return
    text = transcript_text(meeting_id)
    if text:
        await index_text(meeting["owner_id"], "transcript", meeting_id, text)


def extract_document_text(path: Path, mime: str) -> str:
    """Plain-text and PDF extraction. PDF via pypdf if installed; other
    formats can be added behind this function."""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # optional dep
        except ImportError as e:
            raise RuntimeError("PDF support requires 'pypdf' (pip install pypdf)") from e
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise RuntimeError(f"unsupported document type: {suffix}")


async def index_document_job(payload: dict[str, Any]) -> None:
    doc_id = int(payload["document_id"])
    db = get_db()
    doc = db.query_one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if doc is None:
        return
    try:
        from neurai.fa import fa_normalize

        # D5: documents go through fa_normalize like everything else, so an
        # Arabic-typed ي/ك query and a normalized chunk can't diverge.
        text = fa_normalize(extract_document_text(Path(doc["path"]), doc["mime"]))
        await index_text(doc["owner_id"], "document", doc_id, text)
        db.execute("UPDATE documents SET status='indexed' WHERE id=?", (doc_id,))
    except Exception:
        db.execute("UPDATE documents SET status='failed' WHERE id=?", (doc_id,))
        raise
