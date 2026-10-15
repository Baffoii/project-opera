import { describe, expect, it } from 'vitest';
import {
  BAND_COLORS,
  flyToAltitudeM,
  planOverlays,
} from '../../src/opera/globe/overlayPlan.js';

describe('overlay plan', () => {
  const cand = (rank, extra = {}) => ({
    rank,
    lat: 1,
    lon: 2,
    uncertainty_km: 10,
    confidence_band: 'high',
    label: 'x',
    ...extra,
  });
  it('limits to five and converts uncertainty km to metres', () => {
    const plan = planOverlays([1, 2, 3, 4, 5, 6].map((r) => cand(r)));
    expect(plan).toHaveLength(5);
    expect(plan[0].radiusM).toBe(10_000);
    expect(plan[0].color).toBe(BAND_COLORS.high);
  });
  it('omits the circle when uncertainty is unknown', () => {
    expect(
      planOverlays([cand(1, { uncertainty_km: null })])[0].radiusM,
    ).toBeNull();
  });
  it('bounds the fly-to altitude', () => {
    expect(flyToAltitudeM(0)).toBe(15_000);
    expect(flyToAltitudeM(100)).toBeCloseTo(320_000);
    expect(flyToAltitudeM(1e6)).toBe(6_000_000);
  });
});
