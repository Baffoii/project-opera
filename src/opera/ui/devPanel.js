import { h, clear } from './dom.js';

const GEO_ROLE = 'geolocation';

/** Geolocation models the backend knows about, with availability, for the selector. */
export function geoModelOptions(models = []) {
  return models
    .filter((m) => m.role === GEO_ROLE)
    .map((m) => ({
      id: m.id,
      available: m.available !== false,
      reason: m.unavailable_reason ?? null,
      kind: m.kind,
      version: m.version ?? null,
    }));
}

/** Keep the current choice if it is usable; otherwise prefer the real model, then the first usable one. */
export function pickModel(options, current) {
  const usable = options.filter((o) => o.available);
  if (usable.some((o) => o.id === current)) return current;
  return (usable.find((o) => o.kind === 'real') ?? usable[0])?.id ?? current;
}

export function vlmStatus(models = []) {
  const vlm = models.find((m) => m.id === 'vlm-clues');
  if (!vlm) return { available: false, reason: 'unknown' };
  return { available: vlm.available !== false, reason: vlm.unavailable_reason };
}

/** Rows for the "last request" table. Values are shown as the backend reported them. */
export function summarizeRun(analysis, roundTripMs) {
  if (!analysis) return [];
  const rows = [
    [
      'Candidate model',
      `${analysis.model_kind} (${analysis.versions?.geo_adapter ?? 'unknown'})`,
    ],
    ['Clues', analysis.clues_kind ?? 'none'],
  ];
  if (analysis.versions?.clue_model)
    rows.push(['Clue model', analysis.versions.clue_model]);
  const latency = analysis.latency_ms ?? {};
  for (const key of Object.keys(latency))
    rows.push([`Latency: ${key}`, `${Math.round(latency[key])} ms`]);
  if (roundTripMs != null)
    rows.push([
      'Latency: round trip (browser)',
      `${Math.round(roundTripMs)} ms`,
    ]);
  rows.push([
    'Clue cost estimate',
    analysis.cost_estimate_usd == null
      ? 'n/a'
      : `$${analysis.cost_estimate_usd.toFixed(6)}`,
  ]);
  return rows;
}

/**
 * Developer view: choose the geolocation model, toggle VLM clues, inspect the last request.
 * `loadModels` resolves to the backend model list; in frontend-mock mode it is skipped.
 */
export function mountDevPanel(container, { store, loadModels, mock }) {
  const root = h('section', {
    class: 'opera-section opera-dev',
    'aria-label': 'Developer view',
  });
  container.append(root);
  let disposed = false;

  async function refresh() {
    if (mock) return;
    try {
      const models = await loadModels();
      if (disposed) return;
      const model = pickModel(geoModelOptions(models), store.get().model);
      store.set({ models, modelsError: null, model });
    } catch (error) {
      if (!disposed)
        store.set({ modelsError: error?.message || 'Could not load models.' });
    }
  }

  function render() {
    const {
      devViewOpen,
      models,
      modelsError,
      model,
      useVlmClues,
      analysis,
      roundTripMs,
    } = store.get();
    clear(root);
    root.append(
      h(
        'button',
        {
          type: 'button',
          class: 'opera-btn opera-dev-toggle',
          'aria-expanded': String(devViewOpen),
          onclick: () => {
            store.set({ devViewOpen: !devViewOpen });
            if (!devViewOpen) refresh();
          },
        },
        devViewOpen ? 'Developer view ▾' : 'Developer view ▸',
      ),
    );
    if (!devViewOpen) return;

    if (mock) {
      root.append(
        h(
          'p',
          { class: 'opera-muted' },
          'Frontend mock mode (VITE_OPERA_MOCK=1): no backend is called, so model selection is disabled.',
        ),
      );
    } else {
      const options = geoModelOptions(models);
      const select = h(
        'select',
        {
          id: 'opera-model',
          class: 'opera-select',
          onchange: (e) => store.set({ model: e.target.value }),
        },
        options.map((o) => {
          const label = `${o.id}${o.kind === 'mock' ? ' (mock)' : ''}${o.available ? '' : ` - unavailable: ${o.reason}`}`;
          const option = h(
            'option',
            { value: o.id, disabled: !o.available },
            label,
          );
          option.selected = o.id === model;
          return option;
        }),
      );
      root.append(
        h(
          'label',
          { class: 'opera-field', for: 'opera-model' },
          h('span', {}, 'Geolocation model'),
          select,
        ),
      );
      if (modelsError)
        root.append(
          h('p', { class: 'opera-error', role: 'alert' }, modelsError),
        );
      if (!options.length && !modelsError)
        root.append(h('p', { class: 'opera-muted' }, 'Loading models...'));

      const vlm = vlmStatus(models);
      const toggle = h('input', {
        type: 'checkbox',
        id: 'opera-vlm',
        onchange: (e) => store.set({ useVlmClues: e.target.checked }),
      });
      toggle.checked = useVlmClues;
      root.append(
        h(
          'label',
          { class: 'opera-check', for: 'opera-vlm' },
          toggle,
          h('span', {}, 'Extract clues with the VLM'),
        ),
      );
      if (useVlmClues && !vlm.available)
        root.append(
          h(
            'p',
            { class: 'opera-muted' },
            `VLM unavailable (${vlm.reason ?? 'unknown'}): labelled MOCK clues will be shown instead.`,
          ),
        );
    }

    const rows = summarizeRun(analysis, roundTripMs);
    if (rows.length)
      root.append(
        h('h4', { class: 'opera-h' }, 'Last request'),
        h(
          'dl',
          { class: 'opera-kv' },
          rows.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)]),
        ),
      );
  }

  render();
  const unsubscribe = store.subscribe((_s, _p, changed) => {
    if (
      changed.some((k) =>
        [
          'devViewOpen',
          'models',
          'modelsError',
          'model',
          'useVlmClues',
          'analysis',
          'roundTripMs',
        ].includes(k),
      )
    )
      render();
  });
  refresh();
  return {
    refresh,
    destroy() {
      disposed = true;
      unsubscribe();
      root.remove();
    },
  };
}
