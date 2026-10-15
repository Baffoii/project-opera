/** Tiny element builder. Children are always inserted as text nodes, never parsed as HTML. */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs ?? {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function')
      el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(
      child instanceof Node ? child : document.createTextNode(String(child)),
    );
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function mockBadge(text = 'MOCK DATA') {
  return h(
    'span',
    {
      class: 'opera-badge opera-badge-mock',
      title: 'This output is synthetic, not a real model result.',
    },
    text,
  );
}
