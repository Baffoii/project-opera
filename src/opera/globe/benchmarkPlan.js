// Pure description of what a benchmark reveal looks like on the globe (no Cesium dependency).

export const BENCHMARK_COLORS = Object.freeze({
  guess: '#4cc3ff',
  truth: '#3ddc97',
  model: '#f5c542',
  context: '#f5c542',
});

/**
 * Markers, geodesic lines (guess -> truth, model top-1 -> truth) and a bounding box for the camera.
 * Candidates beyond the model's top-1 are drawn as small unnumbered context points.
 */
export function planReveal({ truth, guess = null, model = null }) {
  const markers = [
    { kind: 'truth', lat: truth.lat, lon: truth.lon, label: 'Truth' },
  ];
  const lines = [];
  if (guess) {
    markers.push({
      kind: 'guess',
      lat: guess.lat,
      lon: guess.lon,
      label: 'You',
    });
    lines.push({ kind: 'guess', from: guess, to: truth });
  }
  const candidates = model?.candidates ?? [];
  const top = candidates[0];
  if (top) {
    markers.push({
      kind: 'model',
      lat: top.lat,
      lon: top.lon,
      label: model.status === 'abstained' ? 'Model (abstained)' : 'Model',
    });
    lines.push({ kind: 'model', from: top, to: truth });
    for (const c of candidates.slice(1, 5))
      markers.push({
        kind: 'context',
        lat: c.lat,
        lon: c.lon,
        label: `#${c.rank}`,
      });
  }
  const lats = markers.map((m) => m.lat);
  const lons = markers.map((m) => m.lon);
  return {
    markers: markers.map((m) => ({
      ...m,
      color: BENCHMARK_COLORS[m.kind] ?? '#8aa2b5',
    })),
    lines: lines.map((l) => ({ ...l, color: BENCHMARK_COLORS[l.kind] })),
    bounds: {
      west: Math.min(...lons),
      east: Math.max(...lons),
      south: Math.min(...lats),
      north: Math.max(...lats),
    },
  };
}

/** Pad a bounds box and keep it renderable; a single point gets a fixed margin. */
export function paddedBounds(bounds, padDeg = 4) {
  const pad = Math.max(padDeg, (bounds.east - bounds.west) * 0.15);
  return {
    west: Math.max(bounds.west - pad, -180),
    east: Math.min(bounds.east + pad, 180),
    south: Math.max(bounds.south - pad, -85),
    north: Math.min(bounds.north + pad, 85),
  };
}
