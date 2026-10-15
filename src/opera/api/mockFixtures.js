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

// Benchmark mode fixtures. The "images" are labelled placeholders and the truth locations are arbitrary:
// none of this depicts or measures anything. It exists so the UI can be exercised without a backend.
const MOCK_ROUNDS = [
  { id: 'mock-r1', lat: 48.8566, lon: 2.3522, country: 'FR' },
  { id: 'mock-r2', lat: -33.8688, lon: 151.2093, country: 'AU' },
  { id: 'mock-r3', lat: 35.6762, lon: 139.6503, country: 'JP' },
  { id: 'mock-r4', lat: -1.2921, lon: 36.8219, country: 'KE' },
  { id: 'mock-r5', lat: 40.7128, lon: -74.006, country: 'US' },
];

export function mockBenchmarkDatasets() {
  return [
    {
      id: 'mock-benchmark',
      version: 'mock',
      available: true,
      image_source_types: ['synthetic'],
      splits: {
        seed: { items: 3, images_present: 3 },
        heldout: { items: 5, images_present: 5 },
      },
    },
  ];
}

export function mockPlaceholderImage(index) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400"><rect width="640" height="400" fill="#24384a"/><text x="320" y="190" fill="#8aa2b5" font-family="sans-serif" font-size="28" text-anchor="middle">MOCK IMAGE ${index + 1}</text><text x="320" y="230" fill="#8aa2b5" font-family="sans-serif" font-size="16" text-anchor="middle">placeholder, not a photograph</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function mockBenchmarkRounds({ n = 5 } = {}) {
  return {
    dataset: 'mock-benchmark',
    dataset_version: 'mock',
    split: 'heldout',
    seed: 0,
    rounds: MOCK_ROUNDS.slice(0, n).map((r, index) => ({
      image_id: r.id,
      image_url: mockPlaceholderImage(index),
    })),
  };
}

export function buildMockPlay({ imageId, guess, haversineKm, gameScore }) {
  const index = Math.max(
    0,
    MOCK_ROUNDS.findIndex((r) => r.id === imageId),
  );
  const truth = MOCK_ROUNDS[index];
  const order = seededOrder(index + 7, MOCK_PLACES.length).slice(0, 5);
  const candidates = order.map((placeIndex, i) => {
    const p = MOCK_PLACES[placeIndex];
    return {
      rank: i + 1,
      lat: p.lat,
      lon: p.lon,
      score: Number((0.8 - i * 0.12).toFixed(2)),
      confidence_band: BANDS[i],
      uncalibrated: true,
      error_km: Number(
        haversineKm(truth.lat, truth.lon, p.lat, p.lon).toFixed(1),
      ),
    };
  });
  const abstained = index === 4;
  const userError = guess
    ? Number(haversineKm(truth.lat, truth.lon, guess.lat, guess.lon).toFixed(1))
    : null;
  return {
    dataset: 'mock-benchmark',
    dataset_version: 'mock',
    image_id: truth.id,
    truth: {
      lat: truth.lat,
      lon: truth.lon,
      country: truth.country,
      continent: null,
      settlement_type: 'synthetic',
      landscape: 'synthetic',
      image_source_type: 'synthetic',
    },
    attribution: {
      license: 'none (MOCK placeholder)',
      author: 'OPERA mock fixtures',
      source_url: null,
      license_status: 'needs_human_review',
    },
    user: guess
      ? { guess, error_km: userError, score: gameScore(userError) }
      : null,
    model: {
      id: 'mock',
      version: 'mock-v1',
      kind: 'mock',
      status: abstained ? 'abstained' : 'complete',
      reason: abstained ? 'MOCK: model abstained on this round.' : null,
      abstained,
      candidates,
      top1_error_km: candidates[0].error_km,
      score: abstained ? null : gameScore(candidates[0].error_km),
      latency_ms: 0,
    },
    score_note:
      'Game score = 5000*exp(-km/1492.7). It is a game score, not a model metric.',
  };
}
