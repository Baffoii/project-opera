import { readOperaConfig } from './config.js';
import { createOperaClient } from './api/client.js';
import { createOperaStore } from './state/store.js';
import { h, mockBadge } from './ui/dom.js';
import { mountUploadPanel } from './ui/uploadPanel.js';
import { mountCluesPanel } from './ui/cluesPanel.js';
import { mountCandidatesPanel } from './ui/candidatesPanel.js';
import { mountDevPanel } from './ui/devPanel.js';
import { mountBenchmarkPanel } from './ui/benchmarkPanel.js';

const NO_BENCHMARK_OVERLAYS = Object.freeze({
  enablePicking() {},
  disablePicking() {},
  setGuess() {},
  showReveal() {},
  clear() {},
});

/**
 * Mount OPERA beside the upstream globe. The viewer is only used through the
 * overlay controller; upstream layers and panels are not touched.
 */
export function mountOpera({
  overlays,
  benchmarkOverlays = NO_BENCHMARK_OVERLAYS,
  config = readOperaConfig(),
  client = createOperaClient({ config }),
  store = createOperaStore(),
  host = document.body,
}) {
  const root = h('aside', {
    class: 'opera-root',
    'aria-label': 'OPERA photo geolocation',
  });
  // Upstream binds global keyboard shortcuts; keep typing inside OPERA from triggering them.
  for (const type of ['keydown', 'keyup', 'keypress'])
    root.addEventListener(type, (e) => e.stopPropagation());

  const body = h('div', { class: 'opera-body' });
  const header = h(
    'header',
    { class: 'opera-header' },
    h('strong', { class: 'opera-title' }, 'OPERA'),
    h('span', { class: 'opera-sub' }, 'photo geolocation'),
    client.mock ? mockBadge() : null,
    h(
      'button',
      {
        type: 'button',
        class: 'opera-btn opera-collapse',
        'aria-label': 'Collapse OPERA panel',
        onclick: () => store.set({ panelOpen: false }),
      },
      '–',
    ),
  );
  const launcher = h(
    'button',
    {
      type: 'button',
      class: 'opera-launcher',
      onclick: () => store.set({ panelOpen: true }),
    },
    'OPERA',
  );
  const footer = h(
    'footer',
    { class: 'opera-footer' },
    'Use only photos of public or consented places. Basemap and layer attribution: see "Data attribution" at the bottom-left of the globe.',
  );
  const tabs = h(
    'div',
    { class: 'opera-tabs', role: 'tablist', 'aria-label': 'OPERA mode' },
    ...[
      ['analyze', 'Analyze photo'],
      ['benchmark', 'Benchmark game'],
    ].map(([mode, label]) =>
      h(
        'button',
        {
          type: 'button',
          role: 'tab',
          class: 'opera-btn opera-tab',
          dataset: { mode },
          onclick: () => store.set({ mode }),
        },
        label,
      ),
    ),
  );
  const analyzeBody = h('div', { class: 'opera-mode-analyze' });
  const benchmarkBody = h('div', { class: 'opera-mode-benchmark' });
  const sharedBody = h('div', { class: 'opera-mode-shared' });
  body.append(tabs, analyzeBody, benchmarkBody, sharedBody);
  root.append(header, body, footer);
  host.append(root, launcher);

  let abortController = null;

  async function analyze() {
    const { currentImage, rightsAttested, model, useVlmClues } = store.get();
    if (!currentImage || !rightsAttested) return;
    abortController?.abort();
    abortController = new AbortController();
    store.set({
      status: 'analyzing',
      error: null,
      analysis: null,
      activeCandidateId: null,
      roundTripMs: null,
    });
    const startedAt = performance.now();
    try {
      const analysis = await client.analyze(currentImage.file, {
        model,
        useVlmClues,
        signal: abortController.signal,
      });
      store.set({
        analysis,
        roundTripMs: performance.now() - startedAt,
        status: 'idle',
        activeCandidateId: analysis.candidates?.[0]?.rank ?? null,
      });
      overlays.frameAll();
    } catch (error) {
      if (error?.name === 'AbortError') return;
      store.set({
        status: 'idle',
        error: error?.message || 'Analysis failed.',
      });
    }
  }

  function discard(analysis) {
    abortController?.abort();
    if (analysis?.id) client.deleteAnalysis(analysis.id).catch(() => {});
  }

  const panels = [
    mountUploadPanel(analyzeBody, {
      store,
      maxBytes: config.maxUploadBytes,
      onAnalyze: analyze,
      onRemove: discard,
    }),
    mountCluesPanel(analyzeBody, { store }),
    mountCandidatesPanel(analyzeBody, {
      store,
      onFlyTo: (c) => overlays.flyTo(c),
    }),
    mountBenchmarkPanel(benchmarkBody, {
      store,
      client,
      overlays: benchmarkOverlays,
    }),
    mountDevPanel(sharedBody, {
      store,
      mock: client.mock,
      loadModels: () => client.listModels(),
      loadDatasets: () => client.listDatasets(),
    }),
  ];

  const applyMode = (state) => {
    analyzeBody.hidden = state.mode !== 'analyze';
    benchmarkBody.hidden = state.mode !== 'benchmark';
    for (const tab of tabs.children)
      tab.setAttribute(
        'aria-selected',
        String(tab.dataset.mode === state.mode),
      );
    // Only one mode's markers are on the globe at a time.
    overlays.setCandidates(
      state.mode === 'analyze' ? (state.analysis?.candidates ?? []) : [],
    );
  };

  const unsubscribe = store.subscribe((state, _prev, changed) => {
    if (changed.includes('mode')) applyMode(state);
    if (changed.includes('analysis') && state.mode === 'analyze') {
      overlays.setCandidates(state.analysis?.candidates ?? []);
      overlays.setAttributions(
        (state.analysis?.provenance ?? [])
          .filter((p) => p.role === 'context')
          .map((p) => p.attribution),
      );
    }
    if (changed.includes('activeCandidateId'))
      overlays.setActive(state.activeCandidateId);
    if (changed.includes('panelOpen')) {
      root.hidden = !state.panelOpen;
      launcher.hidden = state.panelOpen;
    }
  });
  launcher.hidden = true;
  applyMode(store.get());

  return {
    store,
    root,
    destroy() {
      unsubscribe();
      abortController?.abort();
      for (const panel of panels) panel.destroy();
      overlays.clear();
      benchmarkOverlays.clear();
      root.remove();
      launcher.remove();
    },
  };
}
