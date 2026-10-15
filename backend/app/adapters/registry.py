from __future__ import annotations

from ..config import Settings, openai_api_key
from .base import ClueAdapter, GeoAdapter
from .mock import MockGeoAdapter, UnavailableClueAdapter, UnavailableGeoAdapter


def build_geo_adapters(settings: Settings) -> dict[str, GeoAdapter]:
    adapters: dict[str, GeoAdapter] = {}
    for adapter in (
        MockGeoAdapter(),
        UnavailableGeoAdapter("geoclip-v1", "geoclip-unreleased", "GeoCLIP runtime is not installed (planned for M3)."),
    ):
        adapters[adapter.id] = adapter
    return adapters


def build_clue_adapters(settings: Settings) -> dict[str, ClueAdapter]:
    if not settings.vlm_enabled:
        reason = "disabled (OPERA_VLM_ENABLED=false)"
    elif not openai_api_key():
        reason = "no key"
    else:
        reason = "adapter not implemented yet (M3)"
    return {"vlm-clues": UnavailableClueAdapter("vlm-clues", "vlm-clues-unreleased", reason)}
