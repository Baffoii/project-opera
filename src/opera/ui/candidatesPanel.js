import { h, clear, mockBadge } from './dom.js';

export function formatCoordinates(lat, lon) {
  const ns = lat >= 0 ? 'N' : 'S';
  const ew = lon >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(3)}°${ns}, ${Math.abs(lon).toFixed(3)}°${ew}`;
}

const CONTEXT_NOTES = {
  unavailable: 'Place name unavailable (lookup failed); coordinates only',
  no_result: 'No place name here (open water or unmapped area)',
  stale: 'Place name from an older cached lookup',
};

export function candidateTitle(c) {
  if (c.label) return c.label;
  return CONTEXT_NOTES[c.context?.status] ?? 'Context unavailable';
}

export function mountCandidatesPanel(container, { store, onFlyTo }) {
  const root = h('section', {
    class: 'opera-section',
    'aria-label': 'Candidate locations',
  });
  container.append(root);

  function render() {
    const { analysis, activeCandidateId } = store.get();
    clear(root);
    root.hidden = !analysis;
    if (!analysis) return;

    const heading = h('h3', { class: 'opera-h' }, 'Candidate locations');
    if (analysis.model_kind === 'mock') heading.append(' ', mockBadge());
    root.append(heading);

    if (analysis.status === 'failed') {
      root.append(
        h('p', { class: 'opera-muted' }, 'No candidates: the analysis failed.'),
      );
    } else if (analysis.status === 'abstained') {
      root.append(
        h(
          'p',
          { class: 'opera-muted' },
          'No candidates: the model abstained rather than guess.',
        ),
      );
    } else if (!analysis.candidates?.length) {
      root.append(
        h('p', { class: 'opera-muted' }, 'No candidates were returned.'),
      );
    } else {
      root.append(
        h(
          'p',
          { class: 'opera-note' },
          'Scores are raw, uncalibrated model scores, not probabilities. Confidence bands are provisional.',
        ),
      );
      const list = h('ol', { class: 'opera-candidates' });
      for (const c of analysis.candidates.slice(0, 5)) {
        const active = c.rank === activeCandidateId;
        list.append(
          h(
            'li',
            {
              class: `opera-candidate${active ? ' is-active' : ''}`,
              'aria-current': active ? 'true' : null,
              onclick: () => store.set({ activeCandidateId: c.rank }),
            },
            h('span', { class: 'opera-rank' }, c.rank),
            h(
              'div',
              { class: 'opera-candidate-body' },
              h('strong', {}, candidateTitle(c)),
              h('small', {}, formatCoordinates(c.lat, c.lon)),
              h(
                'small',
                {},
                `score ${c.score.toFixed(2)} · `,
                h(
                  'span',
                  { class: `opera-band opera-band-${c.confidence_band}` },
                  c.confidence_band,
                ),
                c.uncalibrated ? ' (uncalibrated)' : '',
                c.uncertainty_km != null ? ` · ±${c.uncertainty_km} km` : '',
              ),
              c.label && c.context?.status === 'stale'
                ? h('small', { class: 'opera-muted' }, CONTEXT_NOTES.stale)
                : null,
              h('small', { class: 'opera-muted' }, `model: ${c.source_model}`),
            ),
            h(
              'button',
              {
                type: 'button',
                class: 'opera-btn',
                'aria-label': `Fly to candidate ${c.rank}`,
                onclick: (e) => {
                  e.stopPropagation();
                  store.set({ activeCandidateId: c.rank });
                  onFlyTo?.(c);
                },
              },
              'Fly to',
            ),
          ),
        );
      }
      root.append(list);
    }

    const attributions = [
      ...new Set(
        (analysis.provenance ?? []).map((p) => p.attribution).filter(Boolean),
      ),
    ];
    if (attributions.length)
      root.append(
        h(
          'p',
          { class: 'opera-attribution' },
          'Data: ',
          attributions.join(' · '),
        ),
      );
  }

  render();
  const unsubscribe = store.subscribe((_s, _p, changed) => {
    if (changed.includes('analysis') || changed.includes('activeCandidateId'))
      render();
  });
  return {
    destroy() {
      unsubscribe();
      root.remove();
    },
  };
}
