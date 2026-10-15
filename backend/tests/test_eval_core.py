from __future__ import annotations

import csv
import hashlib
import io

import pytest
from PIL import Image

from app.adapters.base import GeoResult, RawCandidate
from app.eval.dataset import (
    DatasetError,
    LeakageError,
    check_leakage,
    load_dataset,
    read_verified,
)
from app.eval.metrics import (
    ItemResult,
    geoguessr_style_score,
    percentile,
    reliability_table,
    slice_metrics,
    summarize,
)
from app.eval.runner import compute_outcome, evaluate_item
from app.eval.synthetic import SYNTHETIC_ID, write_synthetic_dataset
from app.services.sanitize import sanitize_image

from .conftest import make_settings


@pytest.fixture
def bench(tmp_path):
    write_synthetic_dataset(tmp_path / "bench")
    return tmp_path / "bench"


def _rewrite(bench, mutate):
    path = bench / SYNTHETIC_ID / "manifest.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    fields = list(rows[0])
    mutate(rows)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _add_image(bench, row_template, image_id, split, data, ext="png"):
    filename = f"{image_id}.{ext}"
    (bench / SYNTHETIC_ID / "images" / filename).write_bytes(data)
    row = {**row_template, "image_id": image_id, "split": split, "filename": filename, "sha256": hashlib.sha256(data).hexdigest()}
    _rewrite(bench, lambda rows: rows.append(row))


def test_percentile_is_nearest_rank():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 50) == 30.0
    assert percentile(values, 95) == 50.0
    assert percentile(values, 1) == 10.0
    assert percentile([], 50) is None


def test_geoguessr_style_score_curve():
    assert geoguessr_style_score(0) == 5000
    assert geoguessr_style_score(1492.7) == pytest.approx(5000 / 2.718281828, abs=1)
    assert geoguessr_style_score(20000) == 0
    assert geoguessr_style_score(-5) == 5000


def _result(i, error, *, score=0.5, band="high", abstained=False, failed=False, **kw):
    return ItemResult(
        image_id=f"i{i}",
        truth_lat=0.0,
        truth_lon=0.0,
        error_km=None if failed else error,
        top5_errors_km=[] if failed else [error],
        top1_score=score,
        band=band,
        abstained=abstained,
        failed=failed,
        truth_country="FR",
        top1_country="FR" if error < 100 else "DE",
        top5_countries=["FR"] if error < 100 else ["DE"],
        slices={"image_source_type": "user_contributed", "continent": "Europe"},
        **kw,
    )


def test_summarize_threshold_rates_and_failures():
    items = [_result(1, 0.5), _result(2, 20), _result(3, 150), _result(4, 900), _result(5, 0, failed=True)]
    block = summarize(items)
    assert block["n_items"] == 5 and block["n_failed"] == 1
    allb = block["all"]
    assert allb["n"] == 4
    assert allb["median_km"] == pytest.approx(85.0)
    assert allb["within_km"] == {"1": 0.25, "25": 0.5, "200": 0.75, "750": 0.75}
    assert allb["country_accuracy"] == 0.5 and allb["country_n"] == 4


def test_abstention_splits_all_from_answered_and_reliability_ignores_abstained():
    items = [_result(1, 5), _result(2, 900, band="low", abstained=True), _result(3, 500, band="low")]
    block = summarize(items)
    assert block["all"]["n"] == 3 and block["answered"]["n"] == 2
    assert block["abstention_rate"] == pytest.approx(0.3333, abs=1e-4)
    table = {r["band"]: r for r in reliability_table(items)}
    assert table["high"]["hit_rate"] == 1.0
    assert table["low"]["n"] == 1 and table["low"]["hits"] == 0
    assert table["medium"]["hit_rate"] is None


def test_slice_metrics_group_by_value():
    items = [_result(1, 5), _result(2, 500)]
    sliced = slice_metrics(items)
    assert sliced["continent"]["Europe"]["n_items"] == 2
    assert "country" not in sliced or sliced["country"] == {}


def test_dataset_loads_and_selection_is_deterministic(bench):
    ds = load_dataset(bench, SYNTHETIC_ID)
    assert len(ds.items) == 8 and len(ds.version) == 12
    assert [i.image_id for i in ds.select("seed")] == ["syn00", "syn02", "syn04", "syn06"]
    first = [i.image_id for i in ds.select("all", seed=3, limit=3)]
    assert first == [i.image_id for i in ds.select("all", seed=3, limit=3)] and len(first) == 3
    assert first == sorted(first)
    with pytest.raises(DatasetError):
        ds.select("nope")


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda rows: rows[1].update(image_id=rows[0]["image_id"]), "duplicate"),
        (lambda rows: rows[0].update(lat="95"), "out of range"),
        (lambda rows: rows[0].update(lat="abc"), "malformed"),
        (lambda rows: rows[0].update(split="train"), "split"),
        (lambda rows: rows[0].update(filename="../x.png"), "unsafe"),
    ],
)
def test_dataset_rejects_bad_manifests(bench, mutate, message):
    _rewrite(bench, mutate)
    with pytest.raises(DatasetError, match=message):
        load_dataset(bench, SYNTHETIC_ID)


def test_dataset_rejects_missing_columns_and_unsafe_ids(bench):
    path = bench / SYNTHETIC_ID / "manifest.csv"
    path.write_text("image_id,lat\nx,1\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="missing columns"):
        load_dataset(bench, SYNTHETIC_ID)
    for bad in ("../etc", "a/b", ".hidden", ""):
        with pytest.raises(DatasetError):
            load_dataset(bench, bad)
    with pytest.raises(DatasetError, match="not found"):
        load_dataset(bench, "missing")


def test_read_verified_refuses_changed_or_missing_files(bench):
    ds = load_dataset(bench, SYNTHETIC_ID)
    item = ds.items[0]
    assert read_verified(ds, item)
    ds.image_path(item).write_bytes(b"tampered")
    with pytest.raises(DatasetError, match="manifest hash"):
        read_verified(ds, item)
    ds.image_path(item).unlink()
    with pytest.raises(DatasetError, match="not present"):
        read_verified(ds, item)


def test_distinct_images_pass_the_leakage_check(bench):
    check_leakage(load_dataset(bench, SYNTHETIC_ID))


def test_exact_duplicate_across_splits_is_leakage(bench):
    ds = load_dataset(bench, SYNTHETIC_ID)
    template = next(csv.DictReader((bench / SYNTHETIC_ID / "manifest.csv").open()))
    _add_image(bench, template, "dup", "heldout", ds.image_path(ds.items[0]).read_bytes())
    with pytest.raises(LeakageError) as info:
        check_leakage(load_dataset(bench, SYNTHETIC_ID))
    assert any(f["kind"] == "sha256" and {f["a"], f["b"]} == {"syn00", "dup"} for f in info.value.findings)


def test_near_duplicate_across_splits_is_leakage_but_same_split_is_allowed(bench):
    ds = load_dataset(bench, SYNTHETIC_ID)
    template = next(csv.DictReader((bench / SYNTHETIC_ID / "manifest.csv").open()))
    original = Image.open(ds.image_path(ds.items[0])).convert("RGB")
    out = io.BytesIO()
    original.resize((64, 48)).save(out, format="JPEG", quality=70)
    _add_image(bench, template, "near_same", "seed", out.getvalue(), "jpg")
    check_leakage(load_dataset(bench, SYNTHETIC_ID))  # syn00 is seed too: not a split violation
    _add_image(bench, template, "near_cross", "heldout", out.getvalue(), "jpg")
    with pytest.raises(LeakageError) as info:
        check_leakage(load_dataset(bench, SYNTHETIC_ID))
    assert any(f["kind"] == "phash" for f in info.value.findings)


class FixedAdapter:
    id, version, kind = "fixed", "fixed-1", "mock"

    def __init__(self, answers):
        self.answers = answers

    def availability(self):
        return True, None

    def predict(self, image_bytes, *, image_sha256, top_k=5):
        lat, lon, score = self.answers[image_sha256]
        return GeoResult(candidates=[RawCandidate(lat, lon, score, country_code="FR")], stages={"model_load": 0.0})


def test_evaluate_item_scores_distance_band_and_abstention(bench, tmp_path):
    settings = make_settings(tmp_path)
    ds = load_dataset(bench, SYNTHETIC_ID)
    item = ds.items[0]  # Paris
    sanitized = sanitize_image(ds.image_path(item).read_bytes(), max_bytes=settings.max_upload_bytes, max_pixels=settings.max_image_pixels)
    adapter = FixedAdapter({sanitized.sha256: (item.lat, item.lon + 0.1, 0.9)})
    result = evaluate_item(settings, ds, item, adapter, clue_adapter=None, resolver=None, price=lambda *_: None)
    assert not result.failed and not result.abstained
    assert 0 < result.error_km < 10 and result.band == "high" and result.top1_country == "FR"
    low = FixedAdapter({sanitized.sha256: (0.0, 0.0, 0.001)})
    result = evaluate_item(settings, ds, item, low, clue_adapter=None, resolver=None, price=lambda *_: None)
    assert result.abstained and result.error_km > 1000 and result.band == "low"


def test_evaluate_item_marks_unusable_and_failing_items(bench, tmp_path):
    settings = make_settings(tmp_path)
    ds = load_dataset(bench, SYNTHETIC_ID)
    item = ds.items[0]

    class Boom(FixedAdapter):
        def predict(self, *a, **kw):
            raise RuntimeError("secret detail")

    assert evaluate_item(settings, ds, item, Boom({}), clue_adapter=None, resolver=None, price=lambda *_: None).failed
    ds.image_path(item).unlink()
    assert evaluate_item(settings, ds, item, Boom({}), clue_adapter=None, resolver=None, price=lambda *_: None).failed


def test_outcome_hash_ignores_latency_but_not_accuracy():
    a = [_result(1, 5, latency_ms=10.0), _result(2, 500, latency_ms=20.0)]
    b = [_result(1, 5, latency_ms=99.0), _result(2, 500, latency_ms=1.0)]
    c = [_result(1, 5), _result(2, 501)]
    assert compute_outcome(a, []).metrics["reproducible_hash"] == compute_outcome(b, []).metrics["reproducible_hash"]
    assert compute_outcome(a, []).metrics["reproducible_hash"] != compute_outcome(c, []).metrics["reproducible_hash"]
    assert set(compute_outcome(a, []).metrics["by_image_source_type"]) == {"user_contributed"}
