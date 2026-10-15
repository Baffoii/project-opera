import { h, clear, mockBadge } from './dom.js';

export const CLUE_CATEGORIES = [
  ['terrain', 'Terrain'],
  ['vegetation', 'Vegetation'],
  ['climate', 'Climate'],
  ['road', 'Roads / markings'],
  ['architecture', 'Architecture'],
  ['language', 'Language / script'],
  ['signage', 'Signage'],
  ['other', 'Other'],
];

/** Group clues by category in display order, dropping empty groups. */
export function groupClues(clues = []) {
  const known = new Set(CLUE_CATEGORIES.map(([key]) => key));
  return CLUE_CATEGORIES.map(([key, label]) => ({
    key,
    label,
    clues: clues.filter(
      (c) => (known.has(c.category) ? c.category : 'other') === key,
    ),
  })).filter((group) => group.clues.length);
}

export function mountCluesPanel(container, { store }) {
  const root = h('section', {
    class: 'opera-section',
    'aria-label': 'Visible clues',
  });
  container.append(root);

  function render() {
    const { analysis, status } = store.get();
    clear(root);
    if (!analysis) {
      root.hidden = status !== 'analyzing';
      if (status === 'analyzing')
        root.append(
          h('h3', { class: 'opera-h' }, 'Clues'),
          h('p', { class: 'opera-muted' }, 'Reading visible clues...'),
        );
      return;
    }
    root.hidden = false;
    const heading = h('h3', { class: 'opera-h' }, 'Clues');
    if ((analysis.clues_kind ?? analysis.model_kind) === 'mock')
      heading.append(' ', mockBadge());
    root.append(heading);
    const appendNotices = () => {
      for (const notice of analysis.notices ?? [])
        root.append(h('p', { class: 'opera-muted', role: 'note' }, notice));
    };

    if (analysis.status === 'abstained' || analysis.status === 'failed') {
      root.append(
        h(
          'div',
          { class: 'opera-abstain', role: 'status' },
          h(
            'strong',
            {},
            analysis.status === 'failed'
              ? 'Analysis failed'
              : 'Model abstained',
          ),
          h('p', {}, analysis.abstain_reason || 'No reason was given.'),
        ),
      );
      appendNotices();
      return;
    }
    const groups = groupClues(analysis.clues);
    if (!groups.length) {
      root.append(
        h(
          'p',
          { class: 'opera-muted' },
          'No clues were extracted for this image.',
        ),
      );
      appendNotices();
      return;
    }
    root.append(
      h(
        'p',
        { class: 'opera-legend' },
        h('span', { class: 'opera-tag opera-tag-observed' }, 'observed'),
        ' directly visible  ',
        h('span', { class: 'opera-tag opera-tag-speculative' }, 'speculative'),
        ' inferred, weaker',
      ),
    );
    for (const group of groups) {
      root.append(
        h(
          'div',
          { class: 'opera-clue-group' },
          h('h4', {}, group.label),
          h(
            'ul',
            {},
            group.clues.map((clue) =>
              h(
                'li',
                { class: `opera-clue opera-clue-${clue.certainty}` },
                h(
                  'span',
                  { class: `opera-tag opera-tag-${clue.certainty}` },
                  clue.certainty,
                ),
                ' ',
                clue.text,
              ),
            ),
          ),
        ),
      );
    }
    const guesses = analysis.clue_model_region_guesses ?? [];
    if (guesses.length)
      root.append(
        h(
          'p',
          { class: 'opera-muted' },
          'Clue-model region guesses (separate from candidates): ',
          guesses.map((g) => g.region).join(', '),
        ),
      );
    appendNotices();
  }

  render();
  const unsubscribe = store.subscribe((_s, _p, changed) => {
    if (changed.includes('analysis') || changed.includes('status')) render();
  });
  return {
    destroy() {
      unsubscribe();
      root.remove();
    },
  };
}
