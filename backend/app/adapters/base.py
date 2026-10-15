from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Kind = Literal["mock", "real"]


@dataclass
class RawCandidate:
    lat: float
    lon: float
    score: float  # raw model score; NOT a probability
    label: str | None = None
    country_code: str | None = None


@dataclass
class GeoResult:
    candidates: list[RawCandidate]
    latency_ms: float = 0.0


class GeoAdapter(Protocol):
    """A pretrained image->location model. Scores from different adapters are never merged."""

    id: str
    version: str
    kind: Kind

    def availability(self) -> tuple[bool, str | None]:
        """(ready, reason_if_not)."""
        ...

    def predict(self, image_bytes: bytes, *, image_sha256: str, top_k: int = 5) -> GeoResult: ...


@dataclass
class ClueResult:
    clues: list[dict]
    region_guesses: list[str]
    abstain: bool = False
    abstain_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    prompt_version: str = ""
    model_name: str = ""
    latency_ms: float = 0.0
    notices: list[str] = field(default_factory=list)


class ClueAdapter(Protocol):
    id: str
    version: str
    kind: Kind

    def availability(self) -> tuple[bool, str | None]: ...

    def extract(self, image_bytes: bytes, *, mime: str) -> ClueResult: ...
