"""Feature engineering shared by the real and synthetic pipelines.

Given a Graph with elevation, slope, min-elevation, and road attributes, derive
per-edge features used by both the risk model (Phase 2) and the hand-tuned
baseline. We also compute hydrology-flavoured features from the graph itself:

  * flow_accumulation: number of upstream edges draining into an edge's lower
    node, approximated by routing each node's unit runoff downhill along the
    steepest-descent edge and counting pass-through (a D8-style accumulation on
    the road graph -- a documented approximation of true DEM flow accumulation).
  * twi (topographic wetness index): ln(flow_acc / tan(slope)), the standard TWI
    form, clamped for flat edges.
  * dist_to_water_norm: graph-distance (in low-elevation hops) to the nearest
    "water" node (lowest-elevation quantile), min-max normalised.
  * height_above_drainage: elevation above the nearest low/water node.

All features are returned normalised to roughly [0,1] so the hand-tuned logistic
baseline and the learned models see comparable scales. Pure stdlib.
"""

from __future__ import annotations

import math
from collections import deque

from routing.graph import Graph


def _min_max_norm(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    rng = hi - lo
    if rng < 1e-12:
        return {k: 0.0 for k in values}
    return {k: (v - lo) / rng for k, v in values.items()}


def flow_accumulation(graph: Graph) -> dict[int, float]:
    """D8-style flow accumulation on the road graph.

    Each node contributes one unit of runoff that flows to its steepest-descent
    downhill neighbour; accumulation at a node is the total upstream runoff that
    passes through it. Returned per NODE. (Documented approximation of DEM-based
    accumulation for the synthetic substitute; the real pipeline uses the DEM.)
    """
    # steepest-descent successor per node
    down: dict[int, int | None] = {}
    indeg: dict[int, int] = {n: 0 for n in graph.nodes}
    for n in graph.nodes:
        best, best_drop = None, 0.0
        for e in graph.out_edges(n):
            drop = graph.nodes[n].elevation_m - graph.nodes[e.v].elevation_m
            if drop > best_drop:
                best_drop, best = drop, e.v
        down[n] = best
    for n, d in down.items():
        if d is not None:
            indeg[d] = indeg.get(d, 0) + 1

    acc = {n: 1.0 for n in graph.nodes}
    # topological drain order via Kahn's algorithm on the drainage forest
    q = deque([n for n in graph.nodes if indeg[n] == 0])
    processed = 0
    while q:
        n = q.popleft()
        processed += 1
        d = down[n]
        if d is not None:
            acc[d] += acc[n]
            indeg[d] -= 1
            if indeg[d] == 0:
                q.append(d)
    # any residual (cycles from flat areas) left as-is
    return acc


def dist_to_water_hops(graph: Graph, water_quantile: float = 0.1) -> dict[int, float]:
    """BFS hop-distance from each node to the nearest low-elevation 'water' node."""
    elevs = sorted(n.elevation_m for n in graph.nodes.values())
    if not elevs:
        return {}
    thresh = elevs[int(water_quantile * (len(elevs) - 1))]
    water = {n.id for n in graph.nodes.values() if n.elevation_m <= thresh}
    dist = {n: math.inf for n in graph.nodes}
    q = deque()
    for w in water:
        dist[w] = 0.0
        q.append(w)
    # BFS over undirected adjacency (use both in/out)
    while q:
        u = q.popleft()
        neigh = set(graph.neighbors(u)) | {e.u for e in graph.in_edges(u)}
        for v in neigh:
            if dist[v] > dist[u] + 1:
                dist[v] = dist[u] + 1
                q.append(v)
    maxd = max((d for d in dist.values() if math.isfinite(d)), default=1.0) or 1.0
    return {n: (d / maxd if math.isfinite(d) else 1.0) for n, d in dist.items()}


def height_above_drainage(graph: Graph, water_quantile: float = 0.1) -> dict[int, float]:
    elevs = sorted(n.elevation_m for n in graph.nodes.values())
    thresh = elevs[int(water_quantile * (len(elevs) - 1))] if elevs else 0.0
    return {nid: max(0.0, graph.nodes[nid].elevation_m - thresh) for nid in graph.nodes}


def edge_features(graph: Graph) -> dict[int, dict]:
    """Compute the normalised per-edge feature dict used by models + baselines."""
    node_acc = flow_accumulation(graph)
    node_acc_norm = _min_max_norm(node_acc)
    node_elev = {nid: graph.nodes[nid].elevation_m for nid in graph.nodes}
    inv_elev = {k: -v for k, v in node_elev.items()}
    inv_elev_norm = _min_max_norm(inv_elev)  # low elevation -> high value
    d2w = dist_to_water_hops(graph)
    had = height_above_drainage(graph)
    had_norm = _min_max_norm({k: -v for k, v in had.items()})  # low HAND -> high

    # per-edge
    feats: dict[int, dict] = {}
    for e in graph.edges.values():
        lo_node = e.u if node_elev[e.u] <= node_elev[e.v] else e.v
        acc_n = node_acc_norm.get(lo_node, 0.0)
        slope_abs = abs(e.slope_pct)
        twi = math.log((node_acc.get(lo_node, 1.0)) / (math.tan(math.radians(slope_abs)) + 0.01))
        feats[e.id] = {
            "edge_id": e.id,
            "inv_elev_norm": inv_elev_norm.get(lo_node, 0.0),
            "inv_slope_norm": max(0.0, 1.0 - min(1.0, slope_abs / 10.0)),
            "slope_pct": e.slope_pct,
            "twi_raw": twi,
            "flow_acc_norm": acc_n,
            "near_water_norm": 1.0 - d2w.get(lo_node, 1.0),  # closer -> higher
            "hand_norm": had_norm.get(lo_node, 0.0),
            "bridge_flag": 1.0 if e.bridge else 0.0,
            "road_primary": 1.0 if e.road_class == "primary" else 0.0,
            "length_m": e.length_m,
            "min_elev_m": e.min_elev_m,
        }
    # normalise twi across edges
    twi_norm = _min_max_norm({eid: f["twi_raw"] for eid, f in feats.items()})
    for eid, f in feats.items():
        f["twi_norm"] = twi_norm.get(eid, 0.0)
    return feats
