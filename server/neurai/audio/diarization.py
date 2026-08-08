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
    global _diarizer
    if _diarizer is None:
        _diarizer = NoopDiarizer()
    return _diarizer


def set_diarizer(d: Diarizer | None) -> None:
    global _diarizer
    _diarizer = d
