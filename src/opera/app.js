import { readOperaConfig } from './config.js';
import { createOperaClient } from './api/client.js';
import { createOperaStore } from './state/store.js';
import { h, mockBadge } from './ui/dom.js';
import { mountUploadPanel } from './ui/uploadPanel.js';
import { mountCluesPanel } from './ui/cluesPanel.js';
import { mountCandidatesPanel } from './ui/candidatesPanel.js';
import { mountDevPanel } from './ui/devPanel.js';

/**
 * Mount OPERA beside the upstream globe. The viewer is only used through the
 * overlay controller; upstream layers and panels are not touched.
 */
export function mountOpera({
  overlays,
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
    mountUploadPanel(body, {
      store,
      maxBytes: config.maxUploadBytes,
      onAnalyze: analyze,
      onRemove: discard,
    }),
    mountCluesPanel(body, { store }),
    mountCandidatesPanel(body, { store, onFlyTo: (c) => overlays.flyTo(c) }),
    mountDevPanel(body, {
      store,
      mock: client.mock,
      loadModels: () => client.listModels(),
    }),
  ];

  const unsubscribe = store.subscribe((state, _prev, changed) => {
    if (changed.includes('analysis'))
      overlays.setCandidates(state.analysis?.candidates ?? []);
    if (changed.includes('activeCandidateId'))
      overlays.setActive(state.activeCandidateId);
    if (changed.includes('panelOpen')) {
      root.hidden = !state.panelOpen;
      launcher.hidden = state.panelOpen;
    }
  });
  launcher.hidden = true;

  return {
    store,
    root,
    destroy() {
      unsubscribe();
      abortController?.abort();
      for (const panel of panels) panel.destroy();
      overlays.clear();
      root.remove();
      launcher.remove();
    },
  };
}
