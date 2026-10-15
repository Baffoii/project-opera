const EARTH_RADIUS_KM = 6371.0088;
const toRad = (deg) => (deg * Math.PI) / 180;

export function haversineKm(lat1, lon1, lat2, lon2) {
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Game score only (5000 * exp(-km / 1492.7)); it is not a model quality metric. */
export function gameScore(distanceKm) {
  return Math.round(5000 * Math.exp(-Math.max(0, distanceKm) / 1492.7));
}

/** Parse two text inputs into a valid guess, or null when either is blank or out of range. */
export function parseGuess(latText, lonText) {
  if (String(latText).trim() === '' || String(lonText).trim() === '')
    return null;
  const lat = Number(latText);
  const lon = Number(lonText);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  return { lat, lon };
}

export function formatKm(km) {
  if (km == null) return 'n/a';
  return km < 10
    ? `${km.toFixed(1)} km`
    : `${Math.round(km).toLocaleString('en-US')} km`;
}

/** Only http(s) links are rendered as links; anything else is shown as text. */
export function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:'
      ? url.href
      : null;
  } catch {
    return null;
  }
}
