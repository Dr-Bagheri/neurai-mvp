"""Voice-activity endpointing for the live pass.

The live loop buffers mic audio and needs to decide *when* to run the small
ASR model. Strategy: run on trailing silence (utterance boundary) or when the
pending buffer exceeds a max window. Silero VAD is the intended upgrade; this
energy-based endpointer is dependency-free and good enough to drive the loop —
it decides when to transcribe, not what was said.
"""
from __future__ import annotations

import numpy as np

from .asr import SAMPLE_RATE

FRAME_MS = 30
_ENERGY_THRESHOLD = 300.0  # int16 RMS; tuned for close-mic speech, revisit in week 0


def is_speech(frame: np.ndarray) -> bool:
    if frame.size == 0:
        return False
    rms = float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))
    return rms >= _ENERGY_THRESHOLD


def trailing_silence_ms(pcm: bytes) -> int:
    """Milliseconds of silence at the end of a PCM16 buffer."""
    samples = np.frombuffer(pcm, dtype=np.int16)
    frame_len = SAMPLE_RATE * FRAME_MS // 1000
    silent_ms = 0
    pos = samples.size
    while pos > 0:
        frame = samples[max(0, pos - frame_len):pos]
        if is_speech(frame):
            break
        silent_ms += FRAME_MS
        pos -= frame_len
    return silent_ms
