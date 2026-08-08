"""Cloud ASR (D15 — the §2.1-3 invariant amendment).

Audio leaves the server ONLY through this module, only when ALL of:
server_mode == online, the meeting carries its explicit per-meeting
«رونویسی ابری» opt-in, and the provider is configured. Every use is
D12-chained (meeting id + provider host, never content). Any failure falls
back to the local GPU pass in the caller — a transcript is never lost to a
cloud error. Offline/air-gapped: unreachable (gated at the opt-in endpoint
AND re-checked at job run).

Provider: OpenAI-compatible POST {url}/audio/transcriptions with
verbose_json → segments with start/end. Default: Groq whisper-large-v3-turbo.
"""
from __future__ import annotations

import io
import logging
import struct
from typing import Any

import httpx

from neurai.config import get_config
from neurai.db import get_db

from .asr import SAMPLE_RATE, AsrSegment

log = logging.getLogger("neurai.cloud_asr")


def provider_config() -> tuple[str, str, str] | None:
    """(url, key, model) when configured, else None. Secrets from the DPAPI
    store (D8); env values are dev-only fallbacks."""
    from neurai.security import get_secret

    cfg = get_config()
    url = get_secret("cloud_asr_url") or cfg.cloud_asr_url
    key = get_secret("cloud_asr_key") or cfg.cloud_asr_key
    model = get_db().get_setting("cloud_asr_model") or cfg.cloud_asr_model
    if not (url and key and model):
        return None
    return url.rstrip("/"), key, model


def _wav_bytes(pcm: bytes) -> bytes:
    return (
        b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
        + b"data" + struct.pack("<I", len(pcm)) + pcm
    )


async def transcribe_cloud(pcm: bytes, language: str = "fa") -> list[AsrSegment]:
    """Raises on any provider problem — the caller falls back to local."""
    config = provider_config()
    if config is None:
        raise RuntimeError("cloud ASR provider not configured")
    url, key, model = config

    async with httpx.AsyncClient(timeout=600.0) as client:
        r = await client.post(
            f"{url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            data={"model": model, "language": language, "response_format": "verbose_json"},
            files={"file": ("meeting.wav", io.BytesIO(_wav_bytes(pcm)), "audio/wav")},
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()

    segments = data.get("segments")
    out: list[AsrSegment] = []
    if segments:
        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if text:
                out.append(AsrSegment(
                    start_ms=int(float(seg["start"]) * 1000),
                    end_ms=int(float(seg["end"]) * 1000),
                    text=text,
                ))
    elif data.get("text"):
        duration_ms = int(len(pcm) * 1000 / (SAMPLE_RATE * 2))
        out.append(AsrSegment(start_ms=0, end_ms=duration_ms, text=data["text"].strip()))
    return out


def provider_host() -> str:
    config = provider_config()
    if config is None:
        return ""
    return httpx.URL(config[0]).host
