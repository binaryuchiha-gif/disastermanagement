// Pure-JS geo utilities for offline use. No dependencies -> node-testable and
// shares exact formulas with the Python routing library (parity tested).

export const EARTH_R = 6371008.8; // mean Earth radius, metres (matches Python)

export function haversineM(lat1, lon1, lat2, lon2) {
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dp = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dp / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * EARTH_R * Math.asin(Math.min(1, Math.sqrt(a)));
}

// Bearing from point A to B in degrees [0,360).
export function bearingDeg(lat1, lon1, lat2, lon2) {
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const y = Math.sin(dl) * Math.cos(p2);
  const x =
    Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  const brng = (Math.atan2(y, x) * 180) / Math.PI;
  return (brng + 360) % 360;
}

// Perpendicular distance (approx, metres) from point P to segment AB, plus the
// projection fraction t in [0,1]. Used for off-route detection and snapping.
export function pointToSegmentM(plat, plon, alat, alon, blat, blon) {
  // local equirectangular projection around A (fine for city scale)
  const latRef = (alat * Math.PI) / 180;
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos(latRef);
  const ax = 0, ay = 0;
  const bx = (blon - alon) * mPerDegLon;
  const by = (blat - alat) * mPerDegLat;
  const px = (plon - alon) * mPerDegLon;
  const py = (plat - alat) * mPerDegLat;
  const dx = bx - ax, dy = by - ay;
  const len2 = dx * dx + dy * dy;
  let t = len2 === 0 ? 0 : ((px - ax) * dx + (py - ay) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  const cx = ax + t * dx, cy = ay + t * dy;
  const dist = Math.hypot(px - cx, py - cy);
  return { dist, t };
}
