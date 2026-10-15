from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """All configuration comes from the environment / `.env` (git-ignored). Never hardcode keys."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_prefix="OPERA_",
        extra="ignore",
        populate_by_name=True,
    )

    # Auth / network
    api_key: str = ""  # X-OPERA-Key. Empty = every non-health route answers 503 (fail closed).
    cors_origins: str = "http://localhost:4173,http://127.0.0.1:4173,http://localhost:4174"
    audit_salt: str = Field(default_factory=lambda: secrets.token_hex(16))
    rate_limit_per_min: int = 30
    rate_limit_burst: int = 10

    # Storage
    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'opera.sqlite'}"
    storage_dir: Path = BACKEND_DIR / "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    upload_ttl_hours: float = 24.0
    sweep_interval_s: float = 300.0

    # Models
    default_model: str = "geoclip-v1"
    abstain_below_score: float = 0.02
    band_high_at: float = 0.5
    band_medium_at: float = 0.15
    vlm_enabled: bool = True
    vlm_model: str = ""  # OPERA_VLM_MODEL; chosen by the owner from OpenAI's current docs.
    vlm_timeout_s: float = 30.0
    vlm_max_edge_px: int = 1024
    # USD per 1M tokens; set from OpenAI's current pricing page. Unset (0) => cost reported as null.
    vlm_price_input_per_mtok: float = 0.0
    vlm_price_output_per_mtok: float = 0.0
    registry_dir: Path = BACKEND_DIR / "registry"

    # Geographic context (M4)
    context_enabled: bool = True
    context_user_agent: str = "OPERA-research/0.1 (set OPERA_CONTEXT_USER_AGENT with a contact URL)"
    context_base_url: str = "https://nominatim.openstreetmap.org"
    context_timeout_s: float = 3.0
    context_min_interval_s: float = 1.1

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def openai_api_key() -> str | None:
    """OPENAI_API_KEY is the same variable upstream God's Eye View uses for voice."""
    import os

    from dotenv import dotenv_values

    value = os.environ.get("OPENAI_API_KEY")
    if value:
        return value
    for path in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        if path.exists():
            found = dotenv_values(path).get("OPENAI_API_KEY")
            if found:
                return found
    return None
