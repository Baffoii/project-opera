// Deterministic MOCK output. Nothing here is a real prediction; every object is
// labelled `model_kind: "mock"` and the UI shows a MOCK DATA badge for it.

const MOCK_PLACES = [
  { label: 'Lisbon, Portugal', country_code: 'PT', lat: 38.7223, lon: -9.1393 },
  { label: 'Kyoto, Japan', country_code: 'JP', lat: 35.0116, lon: 135.7681 },
  {
    label: 'Cape Town, South Africa',
    country_code: 'ZA',
    lat: -33.9249,
    lon: 18.4241,
  },
  {
    label: 'Valparaiso, Chile',
    country_code: 'CL',
    lat: -33.0472,
    lon: -71.6127,
  },
  { label: 'Tallinn, Estonia', country_code: 'EE', lat: 59.437, lon: 24.7536 },
  { label: 'Oaxaca, Mexico', country_code: 'MX', lat: 17.0732, lon: -96.7266 },
  {
    label: 'Hobart, Australia',
    country_code: 'AU',
    lat: -42.8821,
    lon: 147.3272,
  },
  {
    label: 'Reykjavik, Iceland',
    country_code: 'IS',
    lat: 64.1466,
    lon: -21.9426,
  },
  {
    label: 'Chiang Mai, Thailand',
    country_code: 'TH',
    lat: 18.7883,
    lon: 98.9853,
  },
  { label: 'Bergen, Norway', country_code: 'NO', lat: 60.3913, lon: 5.3221 },
  { label: 'Cusco, Peru', country_code: 'PE', lat: -13.5319, lon: -71.9675 },
  { label: 'Tbilisi, Georgia', country_code: 'GE', lat: 41.7151, lon: 44.8271 },
];

const MOCK_CLUES = [
  {
    category: 'terrain',
    text: 'Hilly terrain with a visible ridgeline',
    certainty: 'observed',
  },
  {
    category: 'vegetation',
    text: 'Broadleaf trees and low shrubs',
    certainty: 'observed',
  },
  {
    category: 'climate',
    text: 'Overcast sky; temperate conditions',
    certainty: 'speculative',
  },
  {
    category: 'road',
    text: 'Vehicles keep to the right; painted centre line',
    certainty: 'observed',
  },
  {
    category: 'architecture',
    text: 'Low-rise masonry buildings with tiled roofs',
    certainty: 'observed',
  },
  {
    category: 'language',
    text: 'Latin script on a shop sign',
    certainty: 'observed',
  },
  {
    category: 'signage',
    text: 'Blue rectangular street-name plate',
    certainty: 'speculative',
  },
];

/** FNV-1a over the file's size and leading bytes; stable across runs and browsers. */
export function hashBytes(bytes, size = bytes.length) {
  let h = 0x811c9dc5;
  const mix = (v) => {
    h ^= v;
    h = Math.imul(h, 0x01000193) >>> 0;
  };
  for (let i = 0; i < 4; i += 1) mix((size >>> (i * 8)) & 0xff);
  const limit = Math.min(bytes.length, 65536);
  for (let i = 0; i < limit; i += 1) mix(bytes[i]);
  return h >>> 0;
}

function seededOrder(seed, count) {
  const order = Array.from({ length: count }, (_, i) => i);
  let s = seed || 1;
  for (let i = count - 1; i > 0; i -= 1) {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    const j = s % (i + 1);
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order;
}

const BANDS = ['high', 'medium', 'medium', 'low', 'low'];

export function buildMockAnalysis({ seed, name = '', now = new Date() }) {
  const id = `mock-${seed.toString(16).padStart(8, '0')}`;
  const created = now.toISOString();
  const expires = new Date(now.getTime() + 24 * 3600 * 1000).toISOString();
  const base = {
    id,
    model_kind: 'mock',
    versions: {
      adapters: { mock: 'mock-v1' },
      prompt: 'none (mock)',
      registry: 'mock',
    },
    provenance: [
      {
        provider: 'OPERA mock fixtures',
        kind: 'mock',
        attribution: 'Synthetic placeholder data. Not a real prediction.',
      },
    ],
    latency_ms: { total: 0 },
    cost_estimate_usd: null,
    created_at: created,
    expires_at: expires,
  };
  if (/abstain/i.test(name)) {
    return {
      ...base,
      status: 'abstained',
      abstain_reason:
        'MOCK: no outdoor or geographic content detected in this image.',
      clues: [],
      clue_model_region_guesses: [],
      candidates: [],
    };
  }
  const order = seededOrder(seed, MOCK_PLACES.length).slice(0, 5);
  const clueOrder = seededOrder(seed ^ 0x9e3779b9, MOCK_CLUES.length);
  return {
    ...base,
    status: 'complete',
    abstain_reason: null,
    clues: clueOrder.slice(0, 6).map((i) => MOCK_CLUES[i]),
    clue_model_region_guesses: [
      {
        region: MOCK_PLACES[order[0]].label.split(', ').pop(),
        note: 'MOCK clue-model guess, kept separate from geolocation candidates.',
        source: 'mock',
      },
    ],
    candidates: order.map((placeIndex, i) => {
      const place = MOCK_PLACES[placeIndex];
      return {
        rank: i + 1,
        lat: place.lat,
        lon: place.lon,
        label: `MOCK: ${place.label}`,
        country_code: place.country_code,
        score: Number((0.92 - i * 0.13).toFixed(2)),
        confidence_band: BANDS[i],
        uncalibrated: true,
        uncertainty_km: [25, 60, 150, 400, 800][i],
        source_model: 'mock-v1',
      };
    }),
  };
}
