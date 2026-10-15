import { h, clear } from './dom.js';
import {
  RIGHTS_ATTESTATION,
  validateImageFile,
  validateImageContent,
} from '../validation.js';

/**
 * Upload panel: drag/drop or pick a JPG/PNG/WebP, validate on the client, show a
 * preview, require a rights attestation, then hand the file to `onAnalyze`.
 */
export function mountUploadPanel(
  container,
  { store, maxBytes, onAnalyze, onRemove },
) {
  const root = h('section', {
    class: 'opera-section',
    'aria-label': 'Upload image',
  });
  container.append(root);

  const input = h('input', {
    type: 'file',
    accept: 'image/jpeg,image/png,image/webp',
    class: 'opera-visually-hidden',
    'aria-label': 'Choose an image file',
  });

  async function accept(file) {
    const meta = validateImageFile(file, { maxBytes });
    if (!meta.ok) return store.set({ error: meta.error });
    const content = await validateImageContent(file);
    if (!content.ok) return store.set({ error: content.error });
    const previous = store.get().currentImage;
    if (previous) URL.revokeObjectURL(previous.previewUrl);
    onRemove?.(store.get().analysis);
    store.set({
      currentImage: {
        file,
        name: file.name,
        size: file.size,
        type: content.type,
        previewUrl: URL.createObjectURL(file),
      },
      error: null,
      analysis: null,
      activeCandidateId: null,
      status: 'idle',
    });
  }

  input.addEventListener('change', () => {
    const file = input.files?.[0];
    input.value = '';
    if (file) accept(file);
  });

  function render() {
    const { currentImage, rightsAttested, status, error } = store.get();
    clear(root);
    root.append(h('h3', { class: 'opera-h' }, 'Photo of a public place'));

    if (!currentImage) {
      const drop = h(
        'div',
        {
          class: 'opera-drop',
          tabindex: '0',
          role: 'button',
          'aria-label': 'Drop an image here or press Enter to choose a file',
          onclick: () => input.click(),
          onkeydown: (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              input.click();
            }
          },
          ondragover: (e) => {
            e.preventDefault();
            drop.classList.add('is-over');
          },
          ondragleave: () => drop.classList.remove('is-over'),
          ondrop: (e) => {
            e.preventDefault();
            drop.classList.remove('is-over');
            const file = e.dataTransfer?.files?.[0];
            if (file) accept(file);
          },
        },
        'Drop a JPG, PNG or WebP here, or click to browse',
        h(
          'small',
          {},
          `Up to ${Math.round(maxBytes / 1048576)} MB. Metadata is stripped on upload.`,
        ),
      );
      root.append(drop);
    } else {
      root.append(
        h(
          'div',
          { class: 'opera-preview' },
          h('img', {
            src: currentImage.previewUrl,
            alt: `Preview of ${currentImage.name}`,
          }),
          h(
            'div',
            { class: 'opera-preview-meta' },
            h('strong', {}, currentImage.name),
            h('small', {}, `${(currentImage.size / 1024).toFixed(0)} KB`),
            h(
              'div',
              { class: 'opera-row' },
              h(
                'button',
                {
                  type: 'button',
                  class: 'opera-btn',
                  onclick: () => input.click(),
                },
                'Replace',
              ),
              h(
                'button',
                {
                  type: 'button',
                  class: 'opera-btn',
                  onclick: () => {
                    URL.revokeObjectURL(currentImage.previewUrl);
                    const prior = store.get().analysis;
                    store.set({
                      currentImage: null,
                      analysis: null,
                      activeCandidateId: null,
                      status: 'idle',
                      error: null,
                    });
                    onRemove?.(prior);
                  },
                },
                'Remove',
              ),
            ),
          ),
        ),
      );
    }

    const attest = h('input', {
      type: 'checkbox',
      id: 'opera-rights',
      checked: rightsAttested,
      onchange: (e) => store.set({ rightsAttested: e.target.checked }),
    });
    attest.checked = rightsAttested;
    root.append(
      h(
        'label',
        { class: 'opera-check', for: 'opera-rights' },
        attest,
        h('span', {}, RIGHTS_ATTESTATION),
      ),
    );

    if (error)
      root.append(h('p', { class: 'opera-error', role: 'alert' }, error));

    const busy = status === 'analyzing';
    root.append(
      h(
        'button',
        {
          type: 'button',
          class: 'opera-btn opera-btn-primary',
          disabled: !currentImage || !rightsAttested || busy,
          onclick: () => onAnalyze?.(),
        },
        busy ? 'Analyzing...' : 'Analyze location',
      ),
    );
    root.append(input);
  }

  render();
  const unsubscribe = store.subscribe((_s, _p, changed) => {
    if (
      changed.some((k) =>
        ['currentImage', 'rightsAttested', 'status', 'error'].includes(k),
      )
    )
      render();
  });
  return {
    destroy() {
      unsubscribe();
      const image = store.get().currentImage;
      if (image) URL.revokeObjectURL(image.previewUrl);
      root.remove();
    },
  };
}
