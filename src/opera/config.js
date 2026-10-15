const env = import.meta.env ?? {};

export const OPERA_MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const OPERA_ACCEPTED_TYPES = Object.freeze([
  'image/jpeg',
  'image/png',
  'image/webp',
]);

/** Runtime configuration. `VITE_OPERA_MOCK=1` serves deterministic fixtures with no backend. */
export function readOperaConfig(source = env) {
  return Object.freeze({
    mock: source.VITE_OPERA_MOCK === '1' || source.VITE_OPERA_MOCK === 'true',
    apiUrl: (source.VITE_OPERA_API_URL || 'http://127.0.0.1:8000').replace(
      /\/+$/,
      '',
    ),
    apiKey: source.VITE_OPERA_API_KEY || '',
    maxUploadBytes:
      Number(source.VITE_OPERA_MAX_UPLOAD_BYTES) || OPERA_MAX_UPLOAD_BYTES,
  });
}
