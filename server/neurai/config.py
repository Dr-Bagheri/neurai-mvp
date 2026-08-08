"""Server configuration.

Everything is overridable via environment variables (NEURAI_*) so the Windows
service installer can configure the engine without editing files. Runtime-
mutable settings (connectivity profile, cloud consent, model choices) live in
the `settings` DB table and are managed through the admin API; the values here
are the boot defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"NEURAI_{name}", default)


@dataclass
class Config:
    # Filesystem layout
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(Path.home() / ".neurai"))))
    # Static webui bundle (built by webui/); served if present.
    webui_dir: Path = field(default_factory=lambda: Path(_env("WEBUI_DIR", str(Path(__file__).resolve().parents[2] / "webui" / "dist"))))

    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8471")))

    # Connectivity profile boot default: air_gapped | auto  (D3/§2.1).
    # "air_gapped" disables every cloud code path outright — no probes, ever.
    connectivity_profile: str = field(default_factory=lambda: _env("PROFILE", "auto"))

    # Local model endpoints
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://127.0.0.1:11434"))
    local_chat_model: str = field(default_factory=lambda: _env("LOCAL_MODEL", "qwen3:8b"))
    embed_model: str = field(default_factory=lambda: _env("EMBED_MODEL", "bge-m3"))

    # Cloud (optional, consent-gated — D3)
    openrouter_url: str = field(default_factory=lambda: _env("OPENROUTER_URL", "https://openrouter.ai/api"))
    openrouter_key: str = field(default_factory=lambda: _env("OPENROUTER_KEY", ""))
    cloud_chat_model: str = field(default_factory=lambda: _env("CLOUD_MODEL", "anthropic/claude-sonnet-5"))

    # ASR engines: "fake" (dev/tests, no models needed) | "faster-whisper"
    asr_engine: str = field(default_factory=lambda: _env("ASR", "faster-whisper"))
    asr_live_model: str = field(default_factory=lambda: _env("ASR_LIVE_MODEL", "small"))
    asr_quality_model: str = field(default_factory=lambda: _env("ASR_QUALITY_MODEL", "large-v3"))
    asr_compute_type: str = field(default_factory=lambda: _env("ASR_COMPUTE", "int8"))

    # Capacity (§4): concurrent live meetings is a config cap, not an architecture limit.
    max_live_meetings: int = field(default_factory=lambda: int(_env("MAX_LIVE_MEETINGS", "1")))

    session_ttl_hours: int = field(default_factory=lambda: int(_env("SESSION_TTL_HOURS", str(24 * 14))))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "neurai.db"

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.recordings_dir, self.documents_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(cfg: Config) -> None:
    """Test hook / programmatic override."""
    global _config
    _config = cfg
