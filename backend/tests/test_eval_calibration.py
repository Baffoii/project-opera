from __future__ import annotations

from app.eval.calibration import calibrate
from app.eval.metrics import ItemResult


def _item(i, score, error):
    return ItemResult(image_id=f"i{i}", truth_lat=0, truth_lon=0, top1_score=score, error_km=error, top5_errors_km=[error])


def test_calibration_finds_bands_from_scores_and_hits():
    items = [_item(i, 0.10 + i * 0.01, 10) for i in range(5)]  # high scores, all hits
    items += [_item(10 + i, 0.03 + i * 0.001, 3000) for i in range(5)]  # middle scores, all misses
    items += [_item(20 + i, 0.001 * (i + 1), 5000) for i in range(6)]  # low scores, misses
    out = calibrate(items)
    t = out["thresholds"]
    assert t["band_high_at"] == 0.034  # five hits plus one miss is 5/6 >= 0.8; a second miss would drop it to 5/7
    assert t["band_medium_at"] == 0.03  # five hits in the top ten is exactly 0.5
    assert t["abstain_below_score"] == 0.03  # lowest hit scored 0.10, capped at the medium cutoff
    assert out["uncertainty_km_p80"]["low"] == 5000 and out["n"] == 16


def test_calibration_declines_to_invent_thresholds_from_thin_data():
    out = calibrate([_item(1, 0.5, 5), _item(2, 0.4, 5)])
    assert out["thresholds"] == {"band_high_at": None, "band_medium_at": None, "abstain_below_score": 0.4}
    assert out["uncertainty_km_p80"] == {"high": None, "medium": None, "low": None}
    assert calibrate([])["thresholds"]["abstain_below_score"] is None


def test_calibration_ignores_failed_items():
    failed = ItemResult(image_id="f", truth_lat=0, truth_lon=0, failed=True)
    assert calibrate([failed])["n"] == 0
