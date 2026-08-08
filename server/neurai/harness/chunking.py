"""Long-input strategies (D3): map-reduce so "fallback to local" actually
works on 2-hour meetings that exceed an 8B model's usable context."""
from __future__ import annotations

from typing import Awaitable, Callable

# Conservative sizing for ~8B q4 models on the 16 GB baseline: keep each map
# call well under the context window, leaving room for the prompt + output.
DEFAULT_CHUNK_CHARS = 8_000
DEFAULT_OVERLAP_CHARS = 400
# Inputs shorter than this skip map-reduce entirely.
SINGLE_SHOT_LIMIT = 12_000


def split_text(
    text: str,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """Split on paragraph/sentence boundaries where possible."""
    if len(text) <= chunk_chars:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        if end < len(text):
            # prefer to break at a newline, then at a sentence end
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind("۔"), window.rfind("."), window.rfind("؟"))
            if cut > chunk_chars // 2:
                end = start + cut + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


async def map_reduce(
    text: str,
    map_fn: Callable[[str, int, int], Awaitable[str]],
    reduce_fn: Callable[[list[str]], Awaitable[str]],
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
) -> str:
    """chunk → per-chunk notes (map) → merge (reduce). Sequential map calls by
    design: the baseline server runs one local model and LLM jobs must not
    starve a live meeting (§4)."""
    chunks = split_text(text, chunk_chars=chunk_chars)
    if not chunks:
        return ""
    if len(chunks) == 1:
        return await map_fn(chunks[0], 0, 1)
    notes = []
    for i, chunk in enumerate(chunks):
        notes.append(await map_fn(chunk, i, len(chunks)))
    return await reduce_fn(notes)
