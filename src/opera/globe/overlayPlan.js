// Pure geometry/styling decisions for candidate overlays (no Cesium dependency, unit-testable).

export const BAND_COLORS = Object.freeze({
  high: '#3ddc97',
  medium: '#f5c542',
  low: '#ff7a59',
});

/** Camera altitude (m) that frames a candidate and its uncertainty circle. */
export function flyToAltitudeM(uncertaintyKm) {
  const radiusM = Math.max(Number(uncertaintyKm) || 0, 1) * 1000;
  return Math.min(Math.max(radiusM * 3.2, 15_000), 6_000_000);
}

/** One overlay description per candidate (max 5), keeping rank order. */
export function planOverlays(candidates = []) {
  return candidates.slice(0, 5).map((c) => ({
    rank: c.rank,
    lat: c.lat,
    lon: c.lon,
    radiusM:
      c.uncertainty_km != null ? Math.max(c.uncertainty_km, 0.1) * 1000 : null,
    color: BAND_COLORS[c.confidence_band] ?? BAND_COLORS.low,
    label: c.label ?? null,
  }));
}
