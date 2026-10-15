import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  formatKm,
  gameScore,
  haversineKm,
  parseGuess,
  safeHttpUrl,
} from '../../src/opera/benchmark/geo.js';
import { summarizeSession } from '../../src/opera/benchmark/session.js';
import {
  paddedBounds,
  planReveal,
} from '../../src/opera/globe/benchmarkPlan.js';
import { createOperaClient } from '../../src/opera/api/client.js';
import { readOperaConfig } from '../../src/opera/config.js';
import { createOperaStore } from '../../src/opera/state/store.js';
import { mountBenchmarkPanel } from '../../src/opera/ui/benchmarkPanel.js';
import {
  summarizeBenchmarkPlay,
  summarizeRegistry,
} from '../../src/opera/ui/devPanel.js';

describe('geometry and scoring', () => {
  it('matches known great-circle distances', () => {
    expect(haversineKm(0, 0, 0, 0)).toBe(0);
    expect(haversineKm(51.5074, -0.1278, 48.8566, 2.3522)).toBeCloseTo(
      343.5,
      -1,
    );
    expect(haversineKm(0, 179.9, 0, -179.9)).toBeCloseTo(22.2, 0);
  });
  it('uses the GeoGuessr-style curve and clamps negatives', () => {
    expect(gameScore(0)).toBe(5000);
    expect(gameScore(-4)).toBe(5000);
    expect(gameScore(1492.7)).toBe(1839);
    expect(gameScore(20000)).toBe(0);
  });
  it('parses guesses strictly', () => {
    expect(parseGuess('48.8', '2.3')).toEqual({ lat: 48.8, lon: 2.3 });
    for (const [a, b] of [
      ['', '1'],
      ['1', ''],
      ['91', '0'],
      ['0', '181'],
      ['x', '1'],
    ])
      expect(parseGuess(a, b)).toBeNull();
  });
  it('only links http(s) sources', () => {
    expect(safeHttpUrl('https://commons.wikimedia.org/x')).toContain(
      'https://',
    );
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull();
    expect(safeHttpUrl('')).toBeNull();
  });
  it('formats distances', () => {
    expect(formatKm(3.14)).toBe('3.1 km');
    expect(formatKm(1234.6)).toBe('1,235 km');
    expect(formatKm(null)).toBe('n/a');
  });
});

describe('session summary', () => {
  const round = (user, model) => ({ user, model });
  it('counts skipped rounds out of the player totals and abstentions out of the model totals', () => {
    const s = summarizeSession([
      round(
        { error_km: 100, score: 4000 },
        { status: 'complete', top1_error_km: 10, score: 4900 },
      ),
      round(null, { status: 'abstained', top1_error_km: 5000, score: null }),
      round({ error_km: 300, score: 3000 }, { status: 'unavailable' }),
    ]);
    expect(s.rounds).toBe(3);
    expect(s.user).toMatchObject({
      played: 2,
      totalScore: 7000,
      medianKm: 200,
      meanKm: 200,
    });
    expect(s.model).toMatchObject({
      answered: 1,
      abstained: 1,
      unavailable: 1,
      totalScore: 4900,
      medianKm: 10,
    });
  });
  it('handles an empty session', () => {
    expect(summarizeSession([]).user.medianKm).toBeNull();
  });
});

describe('reveal plan', () => {
  const truth = { lat: 10, lon: 20 };
  const model = {
    status: 'complete',
    candidates: [1, 2, 3].map((rank) => ({ rank, lat: rank, lon: rank * 2 })),
  };
  it('draws truth, guess and model with a line each', () => {
    const plan = planReveal({ truth, guess: { lat: 0, lon: 0 }, model });
    expect(plan.markers.map((m) => m.kind)).toEqual([
      'truth',
      'guess',
      'model',
      'context',
      'context',
    ]);
    expect(plan.lines.map((l) => l.kind)).toEqual(['guess', 'model']);
    expect(plan.bounds).toEqual({ west: 0, east: 20, south: 0, north: 10 });
  });
  it('omits the guess line when skipped and labels an abstaining model', () => {
    const plan = planReveal({
      truth,
      model: { ...model, status: 'abstained' },
    });
    expect(plan.lines.map((l) => l.kind)).toEqual(['model']);
    expect(plan.markers.find((m) => m.kind === 'model').label).toContain(
      'abstained',
    );
  });
  it('works with no model answer and pads a single point', () => {
    const plan = planReveal({
      truth,
      model: { status: 'unavailable', candidates: [] },
    });
    expect(plan.markers).toHaveLength(1);
    expect(paddedBounds(plan.bounds)).toEqual({
      west: 16,
      east: 24,
      south: 6,
      north: 14,
    });
  });
});

describe('client', () => {
  const mock = () =>
    createOperaClient({
      config: readOperaConfig({ VITE_OPERA_MOCK: '1' }),
      mockDelayMs: 0,
    });
  it('serves labelled mock rounds without the network', async () => {
    const fetchImpl = vi.fn();
    const client = createOperaClient({
      config: readOperaConfig({ VITE_OPERA_MOCK: '1' }),
      mockDelayMs: 0,
      fetchImpl,
    });
    const rounds = await client.benchmarkRounds({ dataset: 'x', n: 3 });
    expect(rounds.rounds).toHaveLength(3);
    const play = await client.benchmarkPlay({
      imageId: rounds.rounds[0].image_id,
      guess: { lat: 48.8566, lon: 2.3522 },
    });
    expect(play.model.kind).toBe('mock');
    expect(play.user).toMatchObject({ error_km: 0, score: 5000 });
    expect(play.model.candidates.every((c) => c.uncalibrated)).toBe(true);
    const skipped = await client.benchmarkPlay({
      imageId: 'mock-r5',
      guess: null,
    });
    expect(skipped.user).toBeNull();
    expect(skipped.model.status).toBe('abstained');
    expect(fetchImpl).not.toHaveBeenCalled();
  });
  it('sends the key and JSON to the real backend and loads images as blobs', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:img');
    const fetchImpl = vi.fn(async (url, init) =>
      url.includes('/images/')
        ? new Response(new Blob(['x']), { status: 200 })
        : new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    const client = createOperaClient({
      config: readOperaConfig({
        VITE_OPERA_API_URL: 'http://api',
        VITE_OPERA_API_KEY: 'k',
      }),
      fetchImpl,
    });
    await client.benchmarkPlay({
      dataset: 'd',
      imageId: 'i',
      model: 'm',
      guess: { lat: 1, lon: 2 },
    });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('http://api/api/v1/benchmark/play');
    expect(init.headers['X-OPERA-Key']).toBe('k');
    expect(JSON.parse(init.body)).toEqual({
      dataset: 'd',
      image_id: 'i',
      model: 'm',
      guess: { lat: 1, lon: 2 },
    });
    expect(await client.benchmarkImage('/api/v1/benchmark/images/d/i')).toBe(
      'blob:img',
    );
    await client.benchmarkRounds({ dataset: 'd', n: 2, seed: 7 });
    expect(fetchImpl.mock.calls[2][0]).toBe(
      'http://api/api/v1/benchmark/rounds?dataset=d&split=heldout&n=2&seed=7',
    );
  });
  it('mock image urls are not revoked', () => {
    URL.revokeObjectURL = vi.fn();
    mock().revokeImage('data:image/svg+xml,x');
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    mock().revokeImage('blob:abc');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:abc');
  });
});

describe('benchmark panel', () => {
  let host;
  let overlays;
  let picked;
  beforeEach(() => {
    document.body.innerHTML = '';
    host = document.createElement('div');
    document.body.append(host);
    picked = null;
    overlays = {
      enablePicking: vi.fn((cb) => (picked = cb)),
      disablePicking: vi.fn(),
      setGuess: vi.fn(),
      showReveal: vi.fn(),
      clear: vi.fn(),
    };
  });
  const mount = () => {
    const client = createOperaClient({
      config: readOperaConfig({ VITE_OPERA_MOCK: '1' }),
      mockDelayMs: 0,
    });
    const store = createOperaStore({ mode: 'benchmark' });
    mountBenchmarkPanel(host, { store, client, overlays });
    return store;
  };
  const tick = () => new Promise((r) => setTimeout(r, 0));
  const click = (selector, text) =>
    [...host.querySelectorAll(selector)]
      .find((b) => !text || b.textContent === text)
      .click();

  it('plays a full game: guess by globe click, reveal, summary', async () => {
    const store = mount();
    expect(host.querySelector('.opera-badge-mock')).not.toBeNull();
    await tick();
    expect(host.textContent).toContain('mock-benchmark');
    click('button', 'Start game');
    await tick();
    await tick();
    expect(
      host.querySelector('.opera-bench-image').getAttribute('src'),
    ).toMatch(/^data:image\/svg/);
    expect(overlays.enablePicking).toHaveBeenCalled();
    expect(
      [...host.querySelectorAll('button')].find(
        (b) => b.textContent === 'Lock in guess',
      ).disabled,
    ).toBe(true);
    picked({ lat: 48.8566, lon: 2.3522 });
    expect(store.get().benchmark.guess).toEqual({ lat: 48.8566, lon: 2.3522 });
    expect(overlays.setGuess).toHaveBeenCalled();
    click('button', 'Lock in guess');
    await tick();
    await tick();
    expect(store.get().benchmark.phase).toBe('revealed');
    expect(host.textContent).toContain('Truth');
    expect(host.textContent).toContain('game score 5000');
    expect(host.textContent).toContain('uncalibrated');
    expect(host.textContent).toContain('licence not yet reviewed');
    expect(overlays.showReveal).toHaveBeenCalledOnce();
    for (let round = 1; round < 5; round += 1) {
      click('button', 'Next round');
      await tick();
      await tick();
      click('button', 'Skip');
      await tick();
      await tick();
    }
    expect(host.textContent).toContain('Model abstained');
    click('button', 'Finish');
    expect(host.textContent).toContain('Game over: 5 rounds');
    expect(host.querySelectorAll('tbody tr').length).toBe(4);
    click('button', 'New game');
    expect(store.get().benchmark.phase).toBe('setup');
    expect(store.get().benchmark.dataset).toBe('mock-benchmark');
  });

  it('is hidden outside benchmark mode and stops picking when leaving it', async () => {
    const store = mount();
    await tick();
    store.set({ mode: 'analyze' });
    expect(host.querySelector('.opera-bench').hidden).toBe(true);
    expect(overlays.disablePicking).toHaveBeenCalled();
    expect(overlays.clear).toHaveBeenCalled();
  });

  it('shows a backend error without losing the round', async () => {
    const client = createOperaClient({
      config: readOperaConfig({ VITE_OPERA_MOCK: '1' }),
      mockDelayMs: 0,
    });
    client.benchmarkPlay = vi
      .fn()
      .mockRejectedValue(new Error('Rate limit exceeded.'));
    const store = createOperaStore({ mode: 'benchmark' });
    mountBenchmarkPanel(host, { store, client, overlays });
    await tick();
    click('button', 'Start game');
    await tick();
    await tick();
    click('button', 'Skip');
    await tick();
    await tick();
    expect(store.get().benchmark.phase).toBe('guessing');
    expect(host.querySelector('[role=alert]').textContent).toBe(
      'Rate limit exceeded.',
    );
  });
});

describe('developer view helpers', () => {
  it('summarizes the last benchmark play and the registry', () => {
    const rows = summarizeBenchmarkPlay({
      dataset: 'd',
      dataset_version: 'v1',
      model: {
        id: 'geoclip-v1',
        version: '1.2.3',
        kind: 'real',
        status: 'complete',
        latency_ms: 812.4,
      },
    });
    expect(rows).toContainEqual(['Benchmark model', 'real (geoclip-v1@1.2.3)']);
    expect(rows).toContainEqual(['Latency: model (excl. load)', '812 ms']);
    expect(summarizeBenchmarkPlay(null)).toEqual([]);
    expect(summarizeRegistry([{ id: 'a' }])).toEqual([
      {
        id: 'a',
        status: 'unknown',
        licenseStatus: 'needs_human_review',
        rights: {},
      },
    ]);
  });
});
