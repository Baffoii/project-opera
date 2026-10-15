import { h, clear, mockBadge } from './dom.js';
import { formatCoordinates } from './candidatesPanel.js';
import { formatKm, parseGuess, safeHttpUrl } from '../benchmark/geo.js';
import {
  initialBenchmarkState,
  summarizeSession,
} from '../benchmark/session.js';

const SPLIT_HELP = {
  heldout: 'heldout: whole places the calibration never saw',
  seed: 'seed: places used to set thresholds',
  all: 'all images',
};

/**
 * GeoGuessr-style mode: look at a metadata-free image, drop a pin (click the globe or type coordinates),
 * then reveal the truth, your distance and the model's candidates. Nothing is stored server-side.
 */
export function mountBenchmarkPanel(container, { store, client, overlays }) {
  const root = h('section', {
    class: 'opera-section opera-bench',
    'aria-label': 'Benchmark game',
  });
  container.append(root);
  let controller = null;
  const get = () => store.get().benchmark;
  const patch = (p) => store.set({ benchmark: { ...get(), ...p } });

  function releaseImage() {
    const { imageUrl } = get();
    if (imageUrl) client.revokeImage?.(imageUrl);
  }

  async function loadDatasets() {
    try {
      const datasets = (await client.listBenchmarkDatasets()).filter(
        (d) => d.available,
      );
      const usable =
        datasets.find((d) => d.splits?.heldout?.images_present > 0) ??
        datasets[0] ??
        null;
      patch({
        datasets,
        datasetsError: null,
        dataset: get().dataset ?? usable?.id ?? null,
      });
    } catch (error) {
      patch({
        datasets: [],
        datasetsError: error?.message || 'Could not load benchmark datasets.',
      });
    }
  }

  async function showRound(index) {
    controller?.abort();
    controller = new AbortController();
    releaseImage();
    overlays.clear();
    patch({
      phase: 'loading',
      index,
      imageUrl: null,
      guess: null,
      result: null,
      error: null,
    });
    try {
      const round = get().rounds[index];
      const imageUrl = await client.benchmarkImage(round.image_url, {
        signal: controller.signal,
      });
      patch({ phase: 'guessing', imageUrl });
      overlays.enablePicking(({ lat, lon }) => {
        const guess = {
          lat: Number(lat.toFixed(4)),
          lon: Number(lon.toFixed(4)),
        };
        patch({ guess });
        overlays.setGuess(guess);
      });
    } catch (error) {
      if (error?.name === 'AbortError') return;
      patch({
        phase: 'guessing',
        error: error?.message || 'Could not load the image.',
      });
    }
  }

  async function start() {
    const { dataset, split, n } = get();
    if (!dataset) return;
    patch({ phase: 'loading', error: null, results: [] });
    try {
      const seed = Math.floor(Math.random() * 2 ** 31);
      const rounds = await client.benchmarkRounds({ dataset, split, n, seed });
      patch({ rounds: rounds.rounds, results: [] });
      await showRound(0);
    } catch (error) {
      patch({
        phase: 'setup',
        error: error?.message || 'Could not start a game.',
      });
    }
  }

  async function reveal(guess) {
    overlays.disablePicking();
    patch({ phase: 'revealing', error: null });
    const { dataset, rounds, index } = get();
    try {
      const result = await client.benchmarkPlay({
        dataset,
        imageId: rounds[index].image_id,
        model: store.get().model,
        guess,
      });
      patch({ phase: 'revealed', result, results: [...get().results, result] });
      overlays.showReveal({
        truth: result.truth,
        guess: result.user?.guess ?? null,
        model: result.model,
      });
    } catch (error) {
      patch({
        phase: 'guessing',
        error: error?.message || 'Could not reveal this round.',
      });
      overlays.enablePicking(({ lat, lon }) => {
        const g = { lat: Number(lat.toFixed(4)), lon: Number(lon.toFixed(4)) };
        patch({ guess: g });
        overlays.setGuess(g);
      });
    }
  }

  function next() {
    const { index, rounds } = get();
    if (index + 1 < rounds.length) return showRound(index + 1);
    overlays.clear();
    releaseImage();
    patch({ phase: 'finished', imageUrl: null });
  }

  function newGame() {
    controller?.abort();
    overlays.disablePicking();
    overlays.clear();
    releaseImage();
    patch({
      ...initialBenchmarkState,
      datasets: get().datasets,
      dataset: get().dataset,
      split: get().split,
      n: get().n,
    });
  }

  const select = (label, value, options, onChange) =>
    h(
      'label',
      { class: 'opera-field' },
      h('span', {}, label),
      h(
        'select',
        { class: 'opera-select', onchange: (e) => onChange(e.target.value) },
        options.map(([v, text, disabled]) =>
          h('option', { value: v, selected: v === value, disabled }, text),
        ),
      ),
    );

  function renderSetup(state) {
    const { datasets, datasetsError, dataset, split, n } = state;
    if (datasets === null)
      return h('p', { class: 'opera-muted' }, 'Loading datasets…');
    if (datasetsError) return h('p', { class: 'opera-error' }, datasetsError);
    if (!datasets.length)
      return h(
        'p',
        { class: 'opera-muted' },
        'No benchmark dataset is available. Run scripts/make_synthetic_benchmark.py or scripts/fetch_benchmark.py in the backend.',
      );
    const current = datasets.find((d) => d.id === dataset);
    const present =
      current?.splits?.[split]?.images_present ?? (split === 'all' ? 1 : 0);
    return h(
      'div',
      { class: 'opera-bench-setup' },
      select(
        'Dataset',
        dataset,
        datasets.map((d) => [
          d.id,
          `${d.id} (${d.image_source_types.join(', ')})`,
        ]),
        (v) => patch({ dataset: v }),
      ),
      select(
        'Images',
        split,
        Object.entries(SPLIT_HELP).map(([v, t]) => [v, t]),
        (v) => patch({ split: v }),
      ),
      select(
        'Rounds',
        String(n),
        [3, 5, 10].map((v) => [String(v), String(v)]),
        (v) => patch({ n: Number(v) }),
      ),
      h(
        'p',
        { class: 'opera-note' },
        `Model: ${store.get().model} (change it in the developer view). Mock models are labelled.`,
      ),
      present === 0
        ? h(
            'p',
            { class: 'opera-muted' },
            'This split has no images on this machine yet (run scripts/fetch_benchmark.py).',
          )
        : null,
      h(
        'button',
        {
          type: 'button',
          class: 'opera-btn opera-btn-primary',
          disabled: present === 0,
          onclick: start,
        },
        'Start game',
      ),
    );
  }

  function renderGuessing(state) {
    const { imageUrl, guess, rounds, index } = state;
    const latInput = h('input', {
      class: 'opera-input',
      type: 'number',
      step: 'any',
      min: -90,
      max: 90,
      'aria-label': 'Guess latitude',
      value: guess?.lat ?? '',
      placeholder: 'lat',
    });
    const lonInput = h('input', {
      class: 'opera-input',
      type: 'number',
      step: 'any',
      min: -180,
      max: 180,
      'aria-label': 'Guess longitude',
      value: guess?.lon ?? '',
      placeholder: 'lon',
    });
    const fromInputs = () => {
      const parsed = parseGuess(latInput.value, lonInput.value);
      patch({ guess: parsed });
      overlays.setGuess(parsed);
    };
    latInput.addEventListener('change', fromInputs);
    lonInput.addEventListener('change', fromInputs);
    return h(
      'div',
      { class: 'opera-bench-round' },
      h(
        'p',
        { class: 'opera-note' },
        `Round ${index + 1} of ${rounds.length}. Click the globe to drop your pin, or type coordinates.`,
      ),
      imageUrl
        ? h('img', {
            class: 'opera-bench-image',
            src: imageUrl,
            alt: 'Benchmark photo to locate',
          })
        : h('p', { class: 'opera-muted' }, 'Loading image…'),
      h('div', { class: 'opera-row' }, latInput, lonInput),
      h(
        'p',
        { class: 'opera-muted' },
        guess
          ? `Your guess: ${formatCoordinates(guess.lat, guess.lon)}`
          : 'No guess yet.',
      ),
      h(
        'div',
        { class: 'opera-row' },
        h(
          'button',
          {
            type: 'button',
            class: 'opera-btn opera-btn-primary',
            disabled: !guess || !imageUrl,
            onclick: () => reveal(guess),
          },
          'Lock in guess',
        ),
        h(
          'button',
          {
            type: 'button',
            class: 'opera-btn',
            disabled: !imageUrl,
            onclick: () => reveal(null),
            title: 'See the answer and the model without guessing',
          },
          'Skip',
        ),
      ),
    );
  }

  function modelBlock(model) {
    const heading = h(
      'h4',
      { class: 'opera-h' },
      `Model: ${model.id} (${model.version})`,
    );
    if (model.kind === 'mock') heading.append(' ', mockBadge());
    const out = [heading];
    if (model.status === 'unavailable' || model.status === 'failed') {
      out.push(
        h('p', { class: 'opera-muted' }, `No model answer: ${model.reason}`),
      );
      return out;
    }
    if (model.status === 'abstained')
      out.push(
        h(
          'p',
          { class: 'opera-abstain' },
          `Model abstained (no game score). ${model.reason ?? ''}`,
        ),
      );
    else
      out.push(
        h(
          'p',
          {},
          `Top-1: ${formatKm(model.top1_error_km)} away, game score ${model.score}`,
        ),
      );
    if (model.candidates.length) {
      out.push(
        h(
          'p',
          { class: 'opera-note' },
          'Raw uncalibrated scores, not probabilities. Candidate distances to the truth:',
        ),
      );
      out.push(
        h(
          'ol',
          { class: 'opera-bench-candidates' },
          model.candidates.map((c) =>
            h(
              'li',
              {},
              `${formatKm(c.error_km)} (score ${c.score}, ${c.confidence_band} band, uncalibrated)`,
            ),
          ),
        ),
      );
    }
    return out;
  }

  function renderRevealed(state) {
    const { result, index, rounds } = state;
    const t = result.truth;
    const url = safeHttpUrl(result.attribution.source_url);
    const place = [t.country, t.continent].filter(Boolean).join(', ');
    return h(
      'div',
      { class: 'opera-bench-reveal' },
      h('h4', { class: 'opera-h' }, 'Truth'),
      h(
        'p',
        { class: 'opera-note' },
        'Globe: green = truth, blue = your guess, yellow = model top-1, small yellow = other candidates.',
      ),
      h(
        'p',
        {},
        `${formatCoordinates(t.lat, t.lon)}${place ? ` (${place})` : ''}`,
      ),
      result.user
        ? h(
            'p',
            {},
            `You: ${formatKm(result.user.error_km)} away, game score ${result.user.score}`,
          )
        : h('p', { class: 'opera-muted' }, 'You skipped this round.'),
      ...modelBlock(result.model),
      h(
        'p',
        { class: 'opera-attribution' },
        `Image: ${result.attribution.author}, ${result.attribution.license} `,
        url
          ? h(
              'a',
              { href: url, target: '_blank', rel: 'noopener noreferrer' },
              'source',
            )
          : null,
        ' (licence not yet reviewed by a human).',
      ),
      h('p', { class: 'opera-note' }, result.score_note),
      h(
        'button',
        { type: 'button', class: 'opera-btn opera-btn-primary', onclick: next },
        index + 1 < rounds.length ? 'Next round' : 'Finish',
      ),
    );
  }

  function renderFinished(state) {
    const s = summarizeSession(state.results);
    const row = (label, user, model) =>
      h(
        'tr',
        {},
        h('th', { scope: 'row' }, label),
        h('td', {}, user),
        h('td', {}, model),
      );
    return h(
      'div',
      { class: 'opera-bench-summary' },
      h('h4', { class: 'opera-h' }, `Game over: ${s.rounds} rounds`),
      h(
        'table',
        { class: 'opera-table' },
        h(
          'thead',
          {},
          h(
            'tr',
            {},
            h('th', {}, ''),
            h('th', {}, 'You'),
            h('th', {}, 'Model'),
          ),
        ),
        h(
          'tbody',
          {},
          row(
            'Rounds answered',
            String(s.user.played),
            String(s.model.answered),
          ),
          row(
            'Total game score',
            String(s.user.totalScore),
            String(s.model.totalScore),
          ),
          row(
            'Median error',
            formatKm(s.user.medianKm),
            formatKm(s.model.medianKm),
          ),
          row(
            'Abstained / unavailable',
            'n/a',
            `${s.model.abstained} / ${s.model.unavailable}`,
          ),
        ),
      ),
      h(
        'p',
        { class: 'opera-note' },
        'A handful of rounds is a game, not an accuracy measurement. See the evaluation endpoints for benchmark metrics.',
      ),
      h(
        'button',
        {
          type: 'button',
          class: 'opera-btn opera-btn-primary',
          onclick: newGame,
        },
        'New game',
      ),
    );
  }

  function render() {
    const state = get();
    clear(root);
    const heading = h('h3', { class: 'opera-h' }, 'Benchmark game');
    if (client.mock) heading.append(' ', mockBadge());
    root.append(heading);
    if (state.error)
      root.append(h('p', { class: 'opera-error', role: 'alert' }, state.error));
    const body =
      state.phase === 'setup'
        ? renderSetup(state)
        : state.phase === 'loading'
          ? h('p', { class: 'opera-muted' }, 'Loading…')
          : state.phase === 'guessing'
            ? renderGuessing(state)
            : state.phase === 'revealing'
              ? h('p', { class: 'opera-muted' }, 'Revealing…')
              : state.phase === 'revealed'
                ? renderRevealed(state)
                : renderFinished(state);
    root.append(body);
    if (state.phase !== 'setup' && state.phase !== 'finished')
      root.append(
        h(
          'button',
          { type: 'button', class: 'opera-btn', onclick: newGame },
          'Quit game',
        ),
      );
  }

  let last = null;
  const unsubscribe = store.subscribe((state, _prev, changed) => {
    if (changed.includes('mode')) {
      root.hidden = state.mode !== 'benchmark';
      if (state.mode === 'benchmark' && state.benchmark.datasets === null)
        loadDatasets();
      if (state.mode !== 'benchmark') {
        overlays.disablePicking();
        overlays.clear();
      }
    }
    const b = state.benchmark;
    const key = [
      b.phase,
      b.index,
      b.imageUrl,
      b.error,
      b.datasets?.length,
      b.dataset,
      b.split,
      b.n,
      b.results.length,
      b.guess?.lat,
      b.guess?.lon,
      state.model,
    ].join('|');
    const relevant = changed.some((k) =>
      ['benchmark', 'mode', 'model'].includes(k),
    );
    if (relevant && (key !== last || changed.includes('mode'))) {
      last = key;
      render();
    }
  });
  root.hidden = store.get().mode !== 'benchmark';
  if (!root.hidden && get().datasets === null) loadDatasets();
  render();

  return {
    destroy() {
      unsubscribe();
      controller?.abort();
      overlays.disablePicking();
      releaseImage();
      root.remove();
    },
  };
}
