// Turn-by-turn instruction generation from route geometry + off-route detection.
// Pure JS, node-testable. Produces a text instruction list usable without the map
// (accessibility / poor visibility).

import { bearingDeg, haversineM, pointToSegmentM } from "./geo.js";

// Classify a bearing change (degrees) into a maneuver.
export function maneuver(deltaDeg) {
  let d = ((deltaDeg + 180) % 360) - 180; // normalize to [-180,180)
  const a = Math.abs(d);
  if (a < 20) return "continue straight";
  const side = d > 0 ? "right" : "left";
  if (a < 60) return `turn slight ${side}`;
  if (a < 120) return `turn ${side}`;
  if (a < 160) return `turn sharp ${side}`;
  return "make a U-turn";
}

// nodes: ordered [{lat,lon,street?}] along the route.
export function buildInstructions(nodes) {
  const steps = [];
  if (nodes.length < 2) return steps;
  let prevBearing = bearingDeg(nodes[0].lat, nodes[0].lon, nodes[1].lat, nodes[1].lon);
  let segDist = haversineM(nodes[0].lat, nodes[0].lon, nodes[1].lat, nodes[1].lon);
  steps.push({ instruction: `Head ${compass(prevBearing)}`, distanceM: Math.round(segDist),
               street: nodes[1].street || null });
  for (let i = 1; i < nodes.length - 1; i++) {
    const b = bearingDeg(nodes[i].lat, nodes[i].lon, nodes[i + 1].lat, nodes[i + 1].lon);
    const dist = haversineM(nodes[i].lat, nodes[i].lon, nodes[i + 1].lat, nodes[i + 1].lon);
    const mv = maneuver(b - prevBearing);
    if (mv !== "continue straight") {
      steps.push({ instruction: `${capitalize(mv)}${nodes[i + 1].street ? " onto " + nodes[i + 1].street : ""}`,
                   distanceM: Math.round(dist), street: nodes[i + 1].street || null });
    } else {
      // merge straight segments into the previous step's distance
      steps[steps.length - 1].distanceM += Math.round(dist);
    }
    prevBearing = b;
  }
  steps.push({ instruction: "Arrive at destination", distanceM: 0, street: null });
  return steps;
}

function compass(deg) {
  const dirs = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"];
  return dirs[Math.round(deg / 45) % 8];
}
function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

// Off-route detection: distance from current fix to the nearest point on the
// remaining route polyline. If > threshold, trigger reroute.
export function deviationM(lat, lon, routeNodes) {
  let best = Infinity;
  for (let i = 0; i < routeNodes.length - 1; i++) {
    const { dist } = pointToSegmentM(
      lat, lon,
      routeNodes[i].lat, routeNodes[i].lon,
      routeNodes[i + 1].lat, routeNodes[i + 1].lon,
    );
    if (dist < best) best = dist;
  }
  return best;
}

export function isOffRoute(lat, lon, routeNodes, thresholdM = 40) {
  return deviationM(lat, lon, routeNodes) > thresholdM;
}
