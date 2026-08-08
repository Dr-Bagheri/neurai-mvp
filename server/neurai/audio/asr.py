"""ASR engine (D2 v0.3): single quality pass, GPU-first.

The live caption pass is gone — during a meeting the server only records
(crash-safe, D11). Transcription is one faster-whisper pass that auto-queues
at meeting end and reports percent progress via `progress_cb`.

Compute (D13 v0.3): exactly one behavior, no setting — load on CUDA with a
forced-initialization probe (CTranslate2 loads cuBLAS lazily, so a missing
CUDA runtime would otherwise crash at first encode, not at build), fall back
to CPU silently on ANY load failure. Logged, never fatal, never a question
the user answers.

Model lineup (D14): large-v3 int8 by default; NEURAI_ASR_MODEL_DIR points at
an alternate local CTranslate2 model directory (the vhdm Persian-turbo
bake-off candidate) with no code change.

`FakeAsrEngine` keeps the whole server + CI runnable with no models.
Audio format everywhere: 16 kHz mono PCM16 little-endian.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

import numpy as np

from neurai.config import get_config
from neurai.fa import fa_normalize

log = logging.getLogger("neurai.asr")

SAMPLE_RATE = 16_000

ProgressCb = Optional[Callable[[float], None]]  # 0.0..1.0


@dataclass
class AsrSegment:
    start_ms: int
    end_ms: int
    text: str


class AsrEngine(Protocol):
    def transcribe(self, pcm: bytes, offset_ms: int = 0, language: str = "fa",
                   progress_cb: ProgressCb = None) -> list[AsrSegment]:
        """Transcribe a PCM16 buffer. offset_ms shifts returned timestamps;
        progress_cb (if given) receives fractions in [0, 1]."""
        ...


class FakeAsrEngine:
    """Deterministic stand-in: one segment per ~3 s of voiced audio.
    Emits progress like the real engine so the meter path is testable."""

    def __init__(self, label: str = "quality"):
        self.label = label

    def transcribe(self, pcm: bytes, offset_ms: int = 0, language: str = "fa",
                   progress_cb: ProgressCb = None) -> list[AsrSegment]:
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size == 0:
            return []
        duration_ms = int(samples.size * 1000 / SAMPLE_RATE)
        # treat near-silent buffers as empty, like a real engine would
        if np.abs(samples).mean() < 50:
            if progress_cb:
                progress_cb(1.0)
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
            if progress_cb:
                progress_cb(min(end / duration_ms, 1.0))
        if progress_cb:
            progress_cb(1.0)
        return segs


def load_gpu_first(try_load: Callable[[str], Any]) -> tuple[Any, str]:
    """D13 v0.3: try CUDA, fall back to CPU on ANY load failure — logged,
    never fatal. `try_load(device)` must force full initialization (probe
    encode) so lazy CUDA library loading can't defer the failure."""
    try:
        return try_load("cuda"), "cuda"
    except Exception as e:
        log.warning("CUDA ASR load failed (%s) — falling back to CPU", e)
        return try_load("cpu"), "cpu"


def _load_whisper(model_ref: str, device: str, compute: str) -> Any:
    """Instantiate WhisperModel, preferring the local cache — a cached model
    must not trigger HuggingFace revision checks (offline-first/D9). For
    CUDA, force initialization NOW with a probe encode: CTranslate2 loads
    cuBLAS lazily at first use, so without this a missing CUDA runtime
    (cublas64_12.dll) would crash mid-pass instead of falling back here."""
    from faster_whisper import WhisperModel  # lazy: optional dep

    try:
        model = WhisperModel(model_ref, device=device, compute_type=compute,
                             local_files_only=True)
    except Exception:  # not cached yet — allow the one-time download
        model = WhisperModel(model_ref, device=device, compute_type=compute)
    if device == "cuda":
        t = np.linspace(0.0, 0.5, SAMPLE_RATE // 2, dtype=np.float32)
        probe = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
        segments, _info = model.transcribe(probe, language="fa", beam_size=1)
        next(iter(segments), None)  # consuming the generator runs encode()
    return model


class FasterWhisperEngine:
    """CTranslate2/faster-whisper — no torch dependency, int8, GPU-first."""

    def __init__(self, model_ref: str | None = None, compute_type: str | None = None):
        cfg = get_config()
        # D14 bake-off hook: a local CT2 model dir wins over the named model
        self._model_ref = model_ref or cfg.asr_model_dir or cfg.asr_quality_model
        self._compute = compute_type or cfg.asr_compute_type
        self._model, self.device = load_gpu_first(
            lambda device: _load_whisper(self._model_ref, device, self._compute),
        )

    def transcribe(self, pcm: bytes, offset_ms: int = 0, language: str = "fa",
                   progress_cb: ProgressCb = None) -> list[AsrSegment]:
        try:
            return self._transcribe(pcm, offset_ms, language, progress_cb)
        except RuntimeError as e:
            # Belt to the load-time probe: if the GPU dies at runtime (driver
            # update, OOM), rebuild on CPU once instead of failing the pass.
            if self.device == "cpu":
                raise
            log.warning("ASR on %s failed at runtime (%s) — rebuilding on CPU", self.device, e)
            self._model = _load_whisper(self._model_ref, "cpu", self._compute)
            self.device = "cpu"
            return self._transcribe(pcm, offset_ms, language, progress_cb)

    def _transcribe(self, pcm: bytes, offset_ms: int, language: str,
                    progress_cb: ProgressCb) -> list[AsrSegment]:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        total_s = max(audio.size / SAMPLE_RATE, 1e-6)
        segments, _info = self._model.transcribe(
            audio, language=language, vad_filter=True, beam_size=5,
        )
        out = []
        for seg in segments:  # generator: progress = consumed audio time
            if progress_cb:
                progress_cb(min(seg.end / total_s, 1.0))
            text = fa_normalize(seg.text.strip()) if language == "fa" else seg.text.strip()
            if not text:
                continue
            out.append(AsrSegment(
                start_ms=offset_ms + int(seg.start * 1000),
                end_ms=offset_ms + int(seg.end * 1000),
                text=text,
            ))
        if progress_cb:
            progress_cb(1.0)
        return out


_quality_engine: AsrEngine | None = None


def get_quality_engine() -> AsrEngine:
    global _quality_engine
    if _quality_engine is None:
        cfg = get_config()
        if cfg.asr_engine == "fake":
            _quality_engine = FakeAsrEngine("quality")
        else:
            _quality_engine = FasterWhisperEngine()
    return _quality_engine


def set_engine(quality: AsrEngine | None) -> None:
    """Test hook."""
    global _quality_engine
    _quality_engine = quality
