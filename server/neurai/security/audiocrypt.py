"""Audio at-rest encryption (D4 — Phase 1 exit criterion, steward ruling).

Recordings are stored as a single sealed file per meeting:

    meeting_<id>.neura  =  MAGIC(6) | nonce(16) | AES-256-CTR(raw PCM16@16k mono)

Design constraints and why CTR:

- **Crash-safety preserved (D2):** CTR is a stream cipher, so each mic chunk
  is encrypted and fsynced the moment it arrives — exactly like the old raw
  `.pcm` path. A crash loses at most the in-flight chunk, and the file needs
  no finalization step at all: recovery is a DB status flip, not a rewrite.
- **Range-seekable playback:** CTR allows decryption from any byte offset
  (keystream position is derived from the offset), so the player can seek to
  any sentence without decrypting the whole meeting.
- Confidentiality is the threat model here (stolen disk, D8); tamper
  *detection* on audio is not a goal — an attacker with write access to the
  data directory is out of scope for MVP (D8).

The 32-byte master key lives in the DPAPI-backed secret store (D8); each file
gets a random 16-byte CTR nonce in its header.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"NRAI1\x00"
HEADER_LEN = len(MAGIC) + 16  # magic + nonce
AUDIO_KEY_NAME = "audio_at_rest_key"


def _master_key() -> bytes:
    from neurai.security import get_or_create_key

    return bytes.fromhex(get_or_create_key(AUDIO_KEY_NAME, nbytes=32))


def _ctr_cipher(nonce: bytes, byte_offset: int):
    """Cipher positioned at `byte_offset` of the keystream (encrypt==decrypt)."""
    block_offset, intra = divmod(byte_offset, 16)
    iv = ((int.from_bytes(nonce, "big") + block_offset) % (1 << 128)).to_bytes(16, "big")
    enc = Cipher(algorithms.AES(_master_key()), modes.CTR(iv)).encryptor()
    if intra:
        enc.update(b"\x00" * intra)  # discard to mid-block position
    return enc


class EncryptedAudioWriter:
    """Append-only encrypted PCM writer. Reopening an existing file resumes
    the keystream where it left off (reconnect after a dropped WS, D2)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.exists() and self.path.stat().st_size >= HEADER_LEN:
            with open(self.path, "rb") as f:
                header = f.read(HEADER_LEN)
            if header[: len(MAGIC)] != MAGIC:
                raise ValueError(f"{self.path.name}: not a NeurAI audio file")
            self._nonce = header[len(MAGIC):]
            offset = self.path.stat().st_size - HEADER_LEN
            self._file = open(self.path, "ab")
        else:
            self._nonce = secrets.token_bytes(16)
            self._file = open(self.path, "wb")
            self._file.write(MAGIC + self._nonce)
            self._file.flush()
            os.fsync(self._file.fileno())
            offset = 0
        self._enc = _ctr_cipher(self._nonce, offset)

    def write(self, chunk: bytes) -> None:
        self._file.write(self._enc.update(chunk))
        self._file.flush()
        os.fsync(self._file.fileno())  # D2: on disk before we ack anything

    def close(self) -> None:
        self._file.close()


def pcm_size(path: str | Path) -> int:
    size = Path(path).stat().st_size
    return max(0, size - HEADER_LEN)


def read_pcm_range(path: str | Path, offset: int = 0, length: int | None = None) -> bytes:
    """Decrypt `length` PCM bytes starting at PCM byte `offset`."""
    path = Path(path)
    with open(path, "rb") as f:
        header = f.read(HEADER_LEN)
        if header[: len(MAGIC)] != MAGIC:
            raise ValueError(f"{path.name}: not a NeurAI audio file")
        nonce = header[len(MAGIC):]
        f.seek(HEADER_LEN + offset)
        data = f.read(length if length is not None else -1)
    return _ctr_cipher(nonce, offset).update(data)


def read_pcm(path: str | Path) -> bytes:
    return read_pcm_range(path, 0, None)
