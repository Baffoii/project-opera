import { OPERA_ACCEPTED_TYPES, OPERA_MAX_UPLOAD_BYTES } from './config.js';

const EXTENSION_TYPES = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
};

/** Identify JPEG/PNG/WebP from magic bytes; returns a MIME type or null. */
export function sniffImageType(bytes) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff)
    return 'image/jpeg';
  if (
    b.length >= 8 &&
    [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every((v, i) => b[i] === v)
  )
    return 'image/png';
  if (
    b.length >= 12 &&
    String.fromCharCode(...b.slice(0, 4)) === 'RIFF' &&
    String.fromCharCode(...b.slice(8, 12)) === 'WEBP'
  )
    return 'image/webp';
  return null;
}

function extensionOf(name) {
  const match = /\.([a-z0-9]+)$/i.exec(String(name ?? ''));
  return match ? match[1].toLowerCase() : '';
}

/**
 * Synchronous checks on file metadata. Magic bytes are checked separately by
 * `validateImageContent`; the server repeats every check and is authoritative.
 */
export function validateImageFile(
  file,
  { maxBytes = OPERA_MAX_UPLOAD_BYTES } = {},
) {
  if (!file) return { ok: false, error: 'Choose an image to analyze.' };
  if (!file.size) return { ok: false, error: 'That file is empty.' };
  if (file.size > maxBytes) {
    const mb = (maxBytes / (1024 * 1024)).toFixed(0);
    return { ok: false, error: `Image is too large. The limit is ${mb} MB.` };
  }
  const declared = file.type || EXTENSION_TYPES[extensionOf(file.name)] || '';
  if (!OPERA_ACCEPTED_TYPES.includes(declared))
    return { ok: false, error: 'Only JPG, PNG or WebP images are accepted.' };
  const ext = EXTENSION_TYPES[extensionOf(file.name)];
  if (ext && ext !== declared)
    return {
      ok: false,
      error: 'The file extension does not match its image type.',
    };
  return { ok: true, error: null };
}

/** Read the leading bytes of a file and confirm they really are JPEG/PNG/WebP. */
export async function validateImageContent(file) {
  const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  const sniffed = sniffImageType(head);
  if (!sniffed)
    return {
      ok: false,
      error: 'That file is not a valid JPG, PNG or WebP image.',
    };
  if (file.type && file.type !== sniffed)
    return {
      ok: false,
      error: 'The file contents do not match its declared image type.',
    };
  return { ok: true, error: null, type: sniffed };
}

export const RIGHTS_ATTESTATION =
  'I have the right to upload this image and it shows a public or consented place.';
