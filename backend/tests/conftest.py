from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.adapters.mock import MockGeoAdapter, UnavailableClueAdapter, UnavailableGeoAdapter
from app.config import Settings
from app.context import AppContext
from app.db import init_db, make_engine, make_session_factory
from app.main import create_app
from app.services.ratelimit import TokenBucketLimiter
from app.services.storage import LocalStorage

API_KEY = "test-key-not-a-secret"
HEADERS = {"X-OPERA-Key": API_KEY}


def make_settings(tmp_path, **overrides) -> Settings:
    base = dict(
        api_key=API_KEY,
        database_url="sqlite://",
        storage_dir=tmp_path / "uploads",
        rate_limit_per_min=6000,
        rate_limit_burst=1000,
        cors_origins="http://localhost:4173",
        audit_salt="test-salt",
        sweep_interval_s=3600,
        max_upload_bytes=200_000,
        max_image_pixels=1_000_000,
        registry_dir=Settings().registry_dir,
        _env_file=None,
    )
    base.update(overrides)
    return Settings(**base)


def make_ctx(settings: Settings, **kw) -> AppContext:
    engine = make_engine(settings.database_url)
    init_db(engine)
    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=make_session_factory(engine),
        storage=LocalStorage(settings.storage_dir),
        geo_adapters={
            "mock": MockGeoAdapter(),
            "geoclip-v1": UnavailableGeoAdapter("geoclip-v1", "x", "not installed"),
        },
        clue_adapters={"vlm-clues": UnavailableClueAdapter("vlm-clues", "x", "no key")},
        limiter=TokenBucketLimiter(settings.rate_limit_per_min, settings.rate_limit_burst),
        **kw,
    )


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def ctx(settings):
    return make_ctx(settings)


@pytest.fixture
def client(settings, ctx):
    with TestClient(create_app(settings, ctx)) as c:
        yield c


@pytest.fixture
def jpeg_bytes() -> Callable[..., bytes]:
    def build(size=(64, 48), color=(200, 30, 30), **save_kwargs) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", size, color).save(buf, format="JPEG", **save_kwargs)
        return buf.getvalue()

    return build


def analyze_files(data: bytes, filename="photo.jpg", content_type="image/jpeg"):
    return {"image": (filename, data, content_type)}


ANALYZE_FORM = {"model": "mock", "rights_attested": "true", "use_vlm_clues": "false"}
