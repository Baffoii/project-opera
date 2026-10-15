from __future__ import annotations

from ..config import Settings
from .base import ClueAdapter, GeoAdapter
from .geoclip import GeoClipAdapter
from .mock import MockClueAdapter, MockGeoAdapter
from .vlm_clues import VlmClueAdapter


def build_geo_adapters(settings: Settings) -> dict[str, GeoAdapter]:
    adapters: list[GeoAdapter] = [MockGeoAdapter(), GeoClipAdapter(settings)]
    return {a.id: a for a in adapters}


def build_clue_adapters(settings: Settings) -> dict[str, ClueAdapter]:
    return {"vlm-clues": VlmClueAdapter(settings), "mock-clues": MockClueAdapter()}
