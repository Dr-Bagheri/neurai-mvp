"""Vector store over SQLite (D4).

Embeddings are float32 blobs in `rag_chunks`; search is brute-force cosine —
completely fine at team-corpus scale, and it keeps the ACL trivially correct:
the candidate set is `WHERE owner_id = ?` *before* similarity is computed
(D7 rule 1 — access control is a WHERE clause). sqlite-vec can replace the
scan later behind this same interface.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from neurai.db import get_db

from .embeddings import get_embeddings

CHUNK_CHARS = 1_200
CHUNK_OVERLAP = 150


@dataclass
class ChunkHit:
    chunk_id: int
    kind: str          # transcript | document
    ref_id: int
    seq: int
    text: str
    score: float


def _split(text: str) -> list[str]:
    from neurai.harness.chunking import split_text

    return split_text(text, chunk_chars=CHUNK_CHARS, overlap=CHUNK_OVERLAP)


async def index_text(owner_id: int, kind: str, ref_id: int, text: str) -> int:
    """(Re)index one resource. Returns number of chunks stored."""
    db = get_db()
    db.execute(
        "DELETE FROM rag_chunks WHERE owner_id=? AND kind=? AND ref_id=?",
        (owner_id, kind, ref_id),
    )
    chunks = _split(text)
    if not chunks:
        return 0
    backend = get_embeddings()
    vectors = await backend.embed(chunks)
    for seq, (chunk, vec) in enumerate(zip(chunks, vectors)):
        db.execute(
            "INSERT INTO rag_chunks(owner_id, kind, ref_id, seq, text, embedding, embed_model) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                owner_id, kind, ref_id, seq, chunk,
                np.asarray(vec, dtype=np.float32).tobytes(), backend.name,
            ),
        )
    return len(chunks)


async def search_chunks(
    owner_id: int,
    query: str,
    top_k: int = 6,
    kind: str | None = None,
) -> list[ChunkHit]:
    """Owner-scoped semantic search. Retrieval is always local (§2.1)."""
    db = get_db()
    sql = "SELECT id, kind, ref_id, seq, text, embedding, embed_model FROM rag_chunks WHERE owner_id=?"
    params: list = [owner_id]
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    rows = db.query(sql, params)
    if not rows:
        return []

    backend = get_embeddings()
    qvec = np.asarray((await backend.embed([query]))[0], dtype=np.float32)
    qnorm = np.linalg.norm(qvec)
    if qnorm == 0:
        return []
    qvec /= qnorm

    hits: list[ChunkHit] = []
    for row in rows:
        if row["embedding"] is None or row["embed_model"] != backend.name:
            continue  # embedded under a different model — needs reindex
        vec = np.frombuffer(row["embedding"], dtype=np.float32)
        if vec.shape != qvec.shape:
            continue
        norm = np.linalg.norm(vec)
        if norm == 0:
            continue
        score = float(np.dot(qvec, vec / norm))
        hits.append(ChunkHit(
            chunk_id=row["id"], kind=row["kind"], ref_id=row["ref_id"],
            seq=row["seq"], text=row["text"], score=score,
        ))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
