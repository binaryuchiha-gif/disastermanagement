// Offline snapping to nearest node/edge via a simple KD-tree spatial index.
// Pure JS (no flatbush dependency needed for the core logic; flatbush is used
// in production for edge bounding boxes, see note). node-testable.

import { haversineM, pointToSegmentM } from "./geo.js";

// Minimal 2D KD-tree over node coordinates (lon=x, lat=y).
export class KDTree {
  constructor(points) {
    // points: [{id, lat, lon}]
    this.points = points;
    this.root = this._build(points.slice(), 0);
  }
  _build(pts, depth) {
    if (pts.length === 0) return null;
    const axis = depth % 2; // 0 -> lon, 1 -> lat
    pts.sort((a, b) => (axis === 0 ? a.lon - b.lon : a.lat - b.lat));
    const mid = Math.floor(pts.length / 2);
    return {
      point: pts[mid],
      axis,
      left: this._build(pts.slice(0, mid), depth + 1),
      right: this._build(pts.slice(mid + 1), depth + 1),
    };
  }
  nearest(lat, lon) {
    let best = { node: null, dist: Infinity };
    const search = (node) => {
      if (!node) return;
      const d = haversineM(lat, lon, node.point.lat, node.point.lon);
      if (d < best.dist) best = { node: node.point, dist: d };
      const axis = node.axis;
      const diff = axis === 0 ? lon - node.point.lon : lat - node.point.lat;
      const near = diff < 0 ? node.left : node.right;
      const far = diff < 0 ? node.right : node.left;
      search(near);
      // approximate degree->metre gate; only descend far side if plausibly closer
      const degGate = (best.dist / 111320) * 1.5;
      if (Math.abs(diff) < degGate) search(far);
    };
    search(this.root);
    return best;
  }
}

// Snap a GPS fix to the nearest edge (returns edge + projection + distance).
// `edges` carry endpoint coords. For large graphs use a bbox index (flatbush);
// here we scan with an early node-based gate for clarity/testability.
export function snapToEdge(lat, lon, edges, maxDistM = 150) {
  let best = { edge: null, dist: Infinity, t: 0 };
  for (const e of edges) {
    const { dist, t } = pointToSegmentM(lat, lon, e.ulat, e.ulon, e.vlat, e.vlon);
    if (dist < best.dist) best = { edge: e, dist, t };
  }
  if (best.dist > maxDistM) return { edge: null, dist: best.dist, outside: true };
  return best;
}

// "GPS outside the graph": true if nearest node is farther than threshold.
export function isOutsideGraph(nearestDistM, thresholdM = 300) {
  return nearestDistM > thresholdM;
}
