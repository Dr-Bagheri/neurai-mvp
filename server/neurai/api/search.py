"""Cross-meeting + document search. Retrieval is always local (§2.1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from neurai.auth.deps import CurrentUser, current_user
from neurai.rag import search_chunks

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    kind: str | None = Field(default=None, pattern="^(transcript|document)$")
    top_k: int = Field(default=8, ge=1, le=30)


@router.post("")
async def search(body: SearchIn, user: CurrentUser = Depends(current_user)):
    hits = await search_chunks(user.id, body.query, top_k=body.top_k, kind=body.kind)
    return [
        {"kind": h.kind, "ref_id": h.ref_id, "seq": h.seq,
         "text": h.text, "score": round(h.score, 4)}
        for h in hits
    ]
