from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ClueCategory = Literal[
    "terrain", "vegetation", "climate", "road", "architecture", "language", "signage", "other"
]


class Clue(BaseModel):
    category: ClueCategory
    text: str = Field(max_length=300)
    certainty: Literal["observed", "speculative"]


class CandidateContext(BaseModel):
    """Place names for a candidate from the context provider (OpenStreetMap Nominatim)."""

    status: Literal["ok", "cached", "stale", "no_result", "unavailable"]
    country: str | None = None
    admin_region: str | None = None
    place: str | None = None


class Candidate(BaseModel):
    rank: int = Field(ge=1, le=5)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str | None = None  # reverse-geocoded, may be None
    country_code: str | None = None
    score: float  # raw model score, NOT a probability
    confidence_band: Literal["low", "medium", "high"]
    uncalibrated: bool = True
    # Heuristic radius derived from the confidence band until calibration exists (M5).
    uncertainty_km: float | None = None
    source_model: str  # adapter id + version
    context: CandidateContext | None = None  # None = context was not requested for this candidate


class Analysis(BaseModel):
    id: str
    status: Literal["pending", "complete", "abstained", "failed"]
    abstain_reason: str | None = None
    model_kind: Literal["mock", "real"]  # kind of the geolocation (candidate) model
    clues_kind: Literal["mock", "real", "none"] = "none"
    clues: list[Clue] = []
    clue_model_region_guesses: list[dict] = []  # kept separate from candidates
    candidates: list[Candidate] = Field(default=[], max_length=5)
    versions: dict = {}
    provenance: list[dict] = []
    notices: list[str] = []
    latency_ms: dict = {}
    cost_estimate_usd: float | None = None
    created_at: datetime
    expires_at: datetime


class VlmClue(BaseModel):
    """Wire schema for the VLM. Deliberately constraint-free (no maxLength/defaults) so OpenAI strict
    Structured Outputs accepts it; limits are enforced after parsing in the adapter."""

    category: ClueCategory
    text: str
    certainty: Literal["observed", "speculative"]


class VlmClueOutput(BaseModel):
    """Strict schema the VLM must fill (used for OpenAI Structured Outputs)."""

    abstain: bool
    abstain_reason: str | None
    clues: list[VlmClue]
    region_guesses: list[str]
