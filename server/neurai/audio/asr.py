"""ASR engines (D2). Two-pass design:

- live pass: small/turbo model, int8, CPU — rough captions, no speakers
- quality pass: Persian fine-tuned large-v3, int8 — authoritative transcript

Engines are pluggable behind `AsrEngine`. `FakeAsrEngine` lets the whole
server (and CI, network-blocked) run without model files: it emits
deterministic placeholder segments so every downstream path is exercised.
faster-whisper is imported lazily — the dependency is optional.

Audio format everywhere: 16 kHz mono PCM16 little-endian.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from neurai.config import get_config
from neurai.fa import fa_normalize

SAMPLE_RATE = 16_000


@dataclass
class AsrSegment:
    start_ms: int
    end_ms: int
    text: str


class AsrEngine(Protocol):
    def transcribe(self, pcm: bytes, offset_ms: int = 0, language: str = "fa") -> list[AsrSegment]:
        """Transcribe a PCM16 buffer. offset_ms shifts returned timestamps."""
        ...


class FakeAsrEngine:
    """Deterministic stand-in: one segment per ~3 s of voiced audio.
    Text marks the window so tests can assert ordering/timing."""

    def __init__(self, label: str = "live"):
        self.label = label

    def transcribe(self, pcm: bytes, offset_ms: int = 0, language: str = "fa") -> list[AsrSegment]:
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size == 0:
            return []
        duration_ms = int(samples.size * 1000 / SAMPLE_RATE)
        # treat near-silent buffers as empty, like a real engine would
        if np.abs(samples).mean() < 50:
            return []
        segs = []
        step = 3000
        for start in range(0, duration_ms, step):
            end = min(start + step, duration_ms)
            if end - start < 300:
                break
            segs.append(AsrSegment(
                start_ms=offset_ms + start,
                end_ms=offset_ms + end,
                text=f"[{self.label}] گفتار آزمایشی {offset_ms + start}",
            ))
        return segs


class FasterWhisperEngine:
    """CTranslate2/faster-whisper — no torch dependency, CPU-first, int8."""

    def __init__(self, model_name: str, compute_type: str | None = None):
        from faster_whisper import WhisperModel  # lazy: optional dep

        cfg = get_config()
        self._model = WhisperModel(
            model_name,
            device="auto",
            compute_type=compute_type or cfg.asr_compute_type,
        )

    def transcribe(self, pcm: bytes, offset_ms: int = 0, language: str = "fa") -> list[AsrSegment]:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _info = self._model.transcribe(
            audio, language=language, vad_filter=True, beam_size=5,
        )
        out = []
        for seg in segments:
            text = fa_normalize(seg.text.strip()) if language == "fa" else seg.text.strip()
            if not text:
                continue
            out.append(AsrSegment(
                start_ms=offset_ms + int(seg.start * 1000),
                end_ms=offset_ms + int(seg.end * 1000),
                text=text,
            ))
        return out


_live_engine: AsrEngine | None = None
_quality_engine: AsrEngine | None = None


def get_live_engine() -> AsrEngine:
    global _live_engine
    if _live_engine is None:
        cfg = get_config()
        if cfg.asr_engine == "fake":
            _live_engine = FakeAsrEngine("live")
        else:
            _live_engine = FasterWhisperEngine(cfg.asr_live_model)
    return _live_engine


def get_quality_engine() -> AsrEngine:
    global _quality_engine
    if _quality_engine is None:
        cfg = get_config()
        if cfg.asr_engine == "fake":
            _quality_engine = FakeAsrEngine("quality")
        else:
            _quality_engine = FasterWhisperEngine(cfg.asr_quality_model)
    return _quality_engine


def set_engines(live: AsrEngine | None, quality: AsrEngine | None) -> None:
    """Test hook."""
    global _live_engine, _quality_engine
    _live_engine = live
    _quality_engine = quality
