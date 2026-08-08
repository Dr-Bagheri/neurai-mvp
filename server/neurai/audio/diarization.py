"""Speaker diarization interface (D2).

The default candidate is 3D-Speaker (Apache-2.0) — pyannote only if its
redistribution terms clear the week-0 license check. Until that adapter
lands, `NoopDiarizer` labels everything S1 so the quality pass, manual
relabel, and export paths all work end-to-end; per-participant capture mode
never needs diarization at all (speaker identity comes from the login).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SpeakerTurn:
    start_ms: int
    end_ms: int
    label: str  # "S1", "S2", …


class Diarizer(Protocol):
    def diarize(self, wav_path: str) -> list[SpeakerTurn]: ...


class NoopDiarizer:
    def diarize(self, wav_path: str) -> list[SpeakerTurn]:
        return []  # empty → all segments default to S1


class PyannoteDiarizer:
    """pyannote speaker-diarization-3.1 (D14; pinned pyannote.audio<4 — 4.x
    has a >9 GB VRAM regression). Optional extra; loaded lazily. Runs AFTER
    ASR in the quality pass so both fit 4 GB VRAM in turn. Decrypts the
    sealed recording in memory — no plaintext audio ever touches disk (D11).
    Gated model: needs a HuggingFace token (NEURAI_HF_TOKEN) accepted once;
    air-gapped sites pre-place the model cache."""

    def __init__(self) -> None:
        import torch
        from pyannote.audio import Pipeline

        from neurai.config import get_config

        token = get_config().hf_token or None
        self._torch = torch
        self._pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=token,
        )
        if torch.cuda.is_available():
            self._pipeline.to(torch.device("cuda"))

    def diarize(self, audio_path: str) -> list[SpeakerTurn]:
        import numpy as np

        from neurai.audio.asr import SAMPLE_RATE
        from neurai.security.audiocrypt import read_pcm

        pcm = np.frombuffer(read_pcm(audio_path), dtype=np.int16)
        waveform = self._torch.from_numpy(
            (pcm.astype("float32") / 32768.0).reshape(1, -1)
        )
        annotation = self._pipeline({"waveform": waveform, "sample_rate": SAMPLE_RATE})
        turns = []
        labels = {}
        for segment, _track, label in annotation.itertracks(yield_label=True):
            if label not in labels:
                labels[label] = f"S{len(labels) + 1}"
            turns.append(SpeakerTurn(
                start_ms=int(segment.start * 1000),
                end_ms=int(segment.end * 1000),
                label=labels[label],
            ))
        return turns


def assign_speakers(segments, turns: list[SpeakerTurn]) -> None:
    """Label each ASR segment with the speaker turn that overlaps it most."""
    for seg in segments:
        best_label, best_overlap = "S1", 0
        for turn in turns:
            overlap = min(seg.end_ms, turn.end_ms) - max(seg.start_ms, turn.start_ms)
            if overlap > best_overlap:
                best_label, best_overlap = turn.label, overlap
        seg.speaker_label = best_label


_diarizer: Diarizer | None = None


def get_diarizer() -> Diarizer:
    """pyannote when the optional extra is installed and loadable; otherwise
    the graceful no-op (offline test suite stays green — segments default to
    S1 and manual relabel still works)."""
    global _diarizer
    if _diarizer is None:
        try:
            _diarizer = PyannoteDiarizer()
        except Exception as e:
            import logging

            logging.getLogger("neurai.audio").info(
                "pyannote diarization unavailable (%s) — skipping diarization", e,
            )
            _diarizer = NoopDiarizer()
    return _diarizer


def set_diarizer(d: Diarizer | None) -> None:
    global _diarizer
    _diarizer = d
