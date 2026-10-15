import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createOperaStore } from '../../src/opera/state/store.js';
import { buildMockAnalysis } from '../../src/opera/api/mockFixtures.js';
import { groupClues, mountCluesPanel } from '../../src/opera/ui/cluesPanel.js';
import { mountCandidatesPanel } from '../../src/opera/ui/candidatesPanel.js';
import { mountUploadPanel } from '../../src/opera/ui/uploadPanel.js';
import {
  geoModelOptions,
  mountDevPanel,
  pickModel,
} from '../../src/opera/ui/devPanel.js';
import { RIGHTS_ATTESTATION } from '../../src/opera/validation.js';

const analysis = (name = 'x.jpg') =>
  buildMockAnalysis({ seed: 1234, name, now: new Date('2026-01-01') });
let host;
beforeEach(() => {
  document.body.innerHTML = '';
  host = document.createElement('div');
  document.body.append(host);
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:preview');
  globalThis.URL.revokeObjectURL = vi.fn();
});

describe('clues panel', () => {
  it('groups by category and styles observed vs speculative distinctly', () => {
    const store = createOperaStore({ analysis: analysis() });
    mountCluesPanel(host, { store });
    expect(host.querySelector('.opera-badge-mock')?.textContent).toBe(
      'MOCK DATA',
    );
    expect(host.querySelectorAll('.opera-clue-group').length).toBeGreaterThan(
      1,
    );
    expect(host.querySelector('.opera-clue-observed')).not.toBeNull();
    expect(host.querySelector('.opera-clue-speculative')).not.toBeNull();
  });
  it('shows an explicit abstained state', () => {
    const store = createOperaStore({ analysis: analysis('abstain.jpg') });
    mountCluesPanel(host, { store });
    expect(host.textContent).toContain('Model abstained');
    expect(host.querySelector('.opera-clue')).toBeNull();
  });
  it('shows backend notices and no MOCK badge when only candidates are mock', () => {
    const real = {
      ...analysis(),
      model_kind: 'mock',
      clues_kind: 'none',
      clues: [],
      notices: ['VLM clues unavailable: no key.'],
    };
    mountCluesPanel(host, { store: createOperaStore({ analysis: real }) });
    expect(host.querySelector('.opera-badge-mock')).toBeNull();
    expect(host.textContent).toContain('VLM clues unavailable: no key.');
  });
  it('shows a failed analysis distinctly from an abstention', () => {
    const failed = {
      ...analysis(),
      status: 'failed',
      abstain_reason: 'mock failed (RuntimeError).',
      candidates: [],
    };
    const store = createOperaStore({ analysis: failed });
    mountCluesPanel(host, { store });
    mountCandidatesPanel(host, { store, onFlyTo: () => {} });
    expect(host.textContent).toContain('Analysis failed');
    expect(host.textContent).toContain('the analysis failed');
    expect(host.textContent).not.toContain('Model abstained');
  });
  it('renders clue text as text, never HTML', () => {
    const evil = {
      ...analysis(),
      clues: [
        {
          category: 'signage',
          text: '<img src=x onerror=alert(1)>',
          certainty: 'observed',
        },
      ],
    };
    mountCluesPanel(host, { store: createOperaStore({ analysis: evil }) });
    expect(host.querySelector('img')).toBeNull();
    expect(host.textContent).toContain('<img src=x');
  });
  it('maps unknown categories to Other', () => {
    expect(
      groupClues([{ category: 'weird', text: 't', certainty: 'observed' }])[0]
        .key,
    ).toBe('other');
  });
});

describe('candidates panel', () => {
  it('renders ranked entries with required fields and caps at 5', () => {
    const a = analysis();
    a.candidates = [...a.candidates, { ...a.candidates[0], rank: 6 }];
    mountCandidatesPanel(host, {
      store: createOperaStore({ analysis: a }),
      onFlyTo: () => {},
    });
    const items = host.querySelectorAll('.opera-candidate');
    expect(items).toHaveLength(5);
    const text = items[0].textContent;
    expect(text).toContain('score 0.92');
    expect(text).toContain('high');
    expect(text).toContain('uncalibrated');
    expect(text).toContain('mock-v1');
    expect(text).toMatch(/°[NS], \d+\.\d+°[EW]/);
    expect(host.textContent).toMatch(/not probabilities/);
    expect(host.querySelector('.opera-attribution').textContent).toMatch(
      /Synthetic/,
    );
  });
  it('Fly to selects the candidate and calls back', () => {
    const store = createOperaStore({ analysis: analysis() });
    const onFlyTo = vi.fn();
    mountCandidatesPanel(host, { store, onFlyTo });
    host.querySelectorAll('button')[2].click();
    expect(onFlyTo).toHaveBeenCalledTimes(1);
    expect(onFlyTo.mock.calls[0][0].rank).toBe(3);
    expect(store.get().activeCandidateId).toBe(3);
    expect(
      host.querySelector('.opera-candidate.is-active .opera-rank').textContent,
    ).toBe('3');
  });
  it('explains abstention instead of listing guesses', () => {
    mountCandidatesPanel(host, {
      store: createOperaStore({ analysis: analysis('abstain.jpg') }),
      onFlyTo() {},
    });
    expect(host.querySelectorAll('.opera-candidate')).toHaveLength(0);
    expect(host.textContent).toMatch(/abstained/);
  });
  it('shows a context-unavailable note when a label is missing', () => {
    const a = analysis();
    a.candidates[0].label = null;
    mountCandidatesPanel(host, {
      store: createOperaStore({ analysis: a }),
      onFlyTo() {},
    });
    expect(host.textContent).toContain('Context unavailable');
  });
  it('distinguishes a failed lookup from open water and still shows coordinates', () => {
    const a = analysis();
    a.candidates[0] = {
      ...a.candidates[0],
      label: null,
      context: { status: 'unavailable' },
    };
    a.candidates[1] = {
      ...a.candidates[1],
      label: null,
      context: { status: 'no_result' },
    };
    mountCandidatesPanel(host, {
      store: createOperaStore({ analysis: a }),
      onFlyTo() {},
    });
    const items = host.querySelectorAll('.opera-candidate');
    expect(items[0].textContent).toContain('Place name unavailable');
    expect(items[0].textContent).toMatch(/°[NS], \d+\.\d+°[EW]/);
    expect(items[1].textContent).toContain('open water or unmapped');
  });
  it('flags names served from a stale cache and shows the OSM attribution from provenance', () => {
    const a = analysis();
    a.candidates[0] = {
      ...a.candidates[0],
      label: 'Lisbon, Portugal',
      context: { status: 'stale', place: 'Lisbon' },
    };
    a.provenance = [
      {
        provider: 'nominatim',
        role: 'context',
        attribution: '© OpenStreetMap contributors',
      },
    ];
    mountCandidatesPanel(host, {
      store: createOperaStore({ analysis: a }),
      onFlyTo() {},
    });
    const first = host.querySelector('.opera-candidate');
    expect(first.textContent).toContain('Lisbon, Portugal');
    expect(first.textContent).toContain('older cached lookup');
    expect(host.querySelector('.opera-attribution').textContent).toBe(
      'Data: © OpenStreetMap contributors',
    );
  });
});

describe('upload panel', () => {
  const png = () =>
    new File(
      [new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0])],
      'p.png',
      { type: 'image/png' },
    );
  const pick = async (file) => {
    const input = host.querySelector('input[type=file]');
    Object.defineProperty(input, 'files', {
      value: [file],
      configurable: true,
    });
    input.dispatchEvent(new Event('change'));
    await vi.waitFor(() =>
      expect(host.querySelector('.opera-preview, .opera-error')).not.toBeNull(),
    );
  };

  it('requires the rights attestation before analysis is enabled', async () => {
    const store = createOperaStore();
    const onAnalyze = vi.fn();
    mountUploadPanel(host, { store, maxBytes: 1e6, onAnalyze });
    const analyzeBtn = () =>
      [...host.querySelectorAll('button')].find((b) =>
        b.textContent.startsWith('Analyze'),
      );
    expect(host.textContent).toContain(RIGHTS_ATTESTATION);
    expect(analyzeBtn().disabled).toBe(true);
    await pick(png());
    expect(host.querySelector('.opera-preview img').getAttribute('src')).toBe(
      'blob:preview',
    );
    expect(analyzeBtn().disabled).toBe(true);
    host.querySelector('#opera-rights').click();
    expect(analyzeBtn().disabled).toBe(false);
    analyzeBtn().click();
    expect(onAnalyze).toHaveBeenCalled();
  });
  it('shows validation errors for bad files and keeps no image', async () => {
    const store = createOperaStore();
    mountUploadPanel(host, { store, maxBytes: 1e6, onAnalyze() {} });
    await pick(new File(['hello'], 'a.gif', { type: 'image/gif' }));
    expect(host.querySelector('.opera-error').textContent).toMatch(
      /JPG, PNG or WebP/,
    );
    expect(store.get().currentImage).toBeNull();
  });
  it('rejects spoofed content', async () => {
    const store = createOperaStore();
    mountUploadPanel(host, { store, maxBytes: 1e6, onAnalyze() {} });
    await pick(
      new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], 'a.jpg', {
        type: 'image/jpeg',
      }),
    );
    expect(host.querySelector('.opera-error').textContent).toMatch(
      /not a valid/,
    );
  });
  it('remove clears the image and discards the prior analysis', async () => {
    const prior = analysis();
    const store = createOperaStore();
    const onRemove = vi.fn();
    mountUploadPanel(host, { store, maxBytes: 1e6, onAnalyze() {}, onRemove });
    await pick(png());
    store.set({ analysis: prior });
    [...host.querySelectorAll('button')]
      .find((b) => b.textContent === 'Remove')
      .click();
    expect(store.get().currentImage).toBeNull();
    expect(store.get().analysis).toBeNull();
    expect(onRemove).toHaveBeenCalledWith(prior);
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });
});

describe('developer panel', () => {
  const models = [
    { id: 'mock', role: 'geolocation', kind: 'mock', available: true },
    {
      id: 'geoclip-v1',
      role: 'geolocation',
      kind: 'real',
      available: false,
      unavailable_reason: 'torch missing',
    },
    {
      id: 'vlm-clues',
      role: 'clues',
      kind: 'real',
      available: false,
      unavailable_reason: 'no key',
    },
  ];

  it('picks the real model when usable, otherwise falls back to a usable one', () => {
    const usable = geoModelOptions(
      models.map((m) =>
        m.id === 'geoclip-v1' ? { ...m, available: true } : m,
      ),
    );
    expect(pickModel(usable, 'mock')).toBe('mock');
    expect(pickModel(usable, 'nope')).toBe('geoclip-v1');
    expect(pickModel(geoModelOptions(models), 'geoclip-v1')).toBe('mock');
  });

  it('lists only geolocation models and disables unavailable ones with the reason', async () => {
    const store = createOperaStore({ devViewOpen: true });
    const panel = mountDevPanel(host, {
      store,
      mock: false,
      loadModels: async () => models,
    });
    await panel.refresh();
    const options = [...host.querySelectorAll('select option')];
    expect(options.map((o) => o.value)).toEqual(['mock', 'geoclip-v1']);
    expect(options[1].disabled).toBe(true);
    expect(options[1].textContent).toContain('torch missing');
    expect(store.get().model).toBe('mock');
    expect(host.textContent).toContain('VLM unavailable (no key)');
    expect(host.textContent).toContain('MOCK clues');
  });

  it('toggles VLM clues in the store and shows last-request latency', async () => {
    const store = createOperaStore({
      devViewOpen: true,
      analysis: {
        model_kind: 'real',
        clues_kind: 'mock',
        versions: { geo_adapter: 'geoclip-v1@geoclip-1.2.3' },
        latency_ms: { geolocate: 2100.4, model_infer: 1800 },
        cost_estimate_usd: null,
      },
      roundTripMs: 2500.2,
    });
    const panel = mountDevPanel(host, {
      store,
      mock: false,
      loadModels: async () => models,
    });
    await panel.refresh();
    const box = host.querySelector('#opera-vlm');
    box.checked = false;
    box.dispatchEvent(new Event('change'));
    expect(store.get().useVlmClues).toBe(false);
    expect(host.textContent).toContain('Latency: geolocate');
    expect(host.textContent).toContain('2100 ms');
    expect(host.textContent).toContain('round trip');
    expect(host.textContent).toContain('geoclip-v1@geoclip-1.2.3');
  });

  it('disables selection in frontend mock mode without calling the backend', () => {
    const loadModels = vi.fn();
    const store = createOperaStore({ devViewOpen: true });
    mountDevPanel(host, { store, mock: true, loadModels });
    expect(loadModels).not.toHaveBeenCalled();
    expect(host.querySelector('select')).toBeNull();
    expect(host.textContent).toContain('Frontend mock mode');
  });

  it('surfaces a model-list failure instead of hiding it', async () => {
    const store = createOperaStore({ devViewOpen: true });
    const panel = mountDevPanel(host, {
      store,
      mock: false,
      loadModels: async () => {
        throw new Error('Could not reach the OPERA backend.');
      },
    });
    await panel.refresh();
    expect(host.querySelector('[role=alert]')?.textContent).toContain(
      'Could not reach',
    );
  });
});
