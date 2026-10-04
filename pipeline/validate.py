"""Graph validation + offline compression (Phase 1). Pure stdlib — RUNS in the
sandbox on the synthetic graph and (locally) on the real graph.

Validation checks:
  * strongly-connected component coverage (routing needs reachability)
  * duplicate edges (same u,v)
  * degenerate geometry (zero/absurd length)
  * coordinate sanity (lat/lon bounds; non-finite)
  * self-loops
Compression:
  * coordinate quantization (round lat/lon to N decimals; ~1 m at 5 dp)
  * drop default-valued attributes to shrink JSON
  * report size before/after
"""

from __future__ import annotations

import json
import math
from collections import deque

from routing.graph import Graph


def _largest_scc_size(graph: Graph) -> int:
    """Tarjan-free: iterative Kosaraju on the directed graph."""
    order = []
    visited = set()

    def dfs_iter(start, adj):
        stack = [(start, iter(adj(start)))]
        visited.add(start)
        local = []
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if nxt not in visited:
                    visited.add(nxt)
                    stack.append((nxt, iter(adj(nxt))))
                    advanced = True
                    break
            if not advanced:
                local.append(node)
                stack.pop()
        return local

    for n in graph.nodes:
        if n not in visited:
            order.extend(dfs_iter(n, graph.neighbors))

    visited.clear()

    def radj(n):
        return [e.u for e in graph.in_edges(n)]

    best = 0
    for n in reversed(order):
        if n not in visited:
            comp = dfs_iter(n, radj)
            best = max(best, len(comp))
    return best


def validate_graph(graph: Graph) -> dict:
    issues = {"duplicate_edges": 0, "zero_length": 0, "self_loops": 0,
              "bad_coords": 0, "nonfinite": 0}
    seen = set()
    for e in graph.edges.values():
        key = (e.u, e.v)
        if key in seen:
            issues["duplicate_edges"] += 1
        seen.add(key)
        if e.length_m <= 0 or e.length_m > 1e6:
            issues["zero_length"] += 1
        if e.u == e.v:
            issues["self_loops"] += 1
        if not math.isfinite(e.length_m):
            issues["nonfinite"] += 1
    for n in graph.nodes.values():
        if not (-90 <= n.lat <= 90 and -180 <= n.lon <= 180):
            issues["bad_coords"] += 1
        if not (math.isfinite(n.lat) and math.isfinite(n.lon)):
            issues["nonfinite"] += 1

    scc = _largest_scc_size(graph)
    return {
        "n_nodes": graph.n_nodes,
        "n_edges": graph.n_edges,
        "largest_scc_nodes": scc,
        "scc_coverage_pct": round(100.0 * scc / max(1, graph.n_nodes), 2),
        "issues": issues,
        "passed": (issues["bad_coords"] == 0 and issues["nonfinite"] == 0
                   and issues["zero_length"] == 0
                   and scc >= 0.6 * graph.n_nodes),
    }


def landmark_snap_test(graph: Graph, landmarks: list[dict]) -> dict:
    """CRS/snapping test: each landmark {name, lat, lon, expect_within_m} must
    snap to a node within the stated distance. Guards EPSG:4326 discipline."""
    results = []
    for lm in landmarks:
        best_d = math.inf
        best_n = None
        for n in graph.nodes.values():
            d = Graph.haversine_m(lm["lat"], lm["lon"], n.lat, n.lon)
            if d < best_d:
                best_d, best_n = d, n.id
        ok = best_d <= lm.get("expect_within_m", 500)
        results.append({"name": lm["name"], "snapped_node": best_n,
                        "distance_m": round(best_d, 1), "ok": ok})
    return {"all_ok": all(r["ok"] for r in results), "landmarks": results}


_EDGE_DEFAULTS = {
    "speed_kph": 30.0, "p_fail": 0.0, "p_fail_lo": 0.0, "p_fail_hi": 0.0,
    "static_risk": 0.0, "road_class": "residential", "lanes": 1,
    "oneway": False, "bridge": False, "tunnel": False, "surface": "paved",
    "slope_pct": 0.0, "min_elev_m": 0.0, "lit": True, "has_stairs": False,
    "capacity_veh_per_h": 600.0,
}


def compact_graph(graph: Graph, quant_decimals: int = 5) -> dict:
    """Quantize coordinates and drop default attributes for offline shipping."""
    nodes = []
    for n in graph.nodes.values():
        nd = {"id": n.id,
              "lat": round(n.lat, quant_decimals),
              "lon": round(n.lon, quant_decimals)}
        if n.elevation_m:
            nd["e"] = round(n.elevation_m, 1)
        if n.is_shelter:
            nd["s"] = n.shelter_capacity
        nodes.append(nd)
    edges = []
    for e in graph.edges.values():
        ed = {"id": e.id, "u": e.u, "v": e.v, "l": round(e.length_m, 1)}
        for attr, default in _EDGE_DEFAULTS.items():
            val = getattr(e, attr)
            if val != default:
                ed[attr] = round(val, 4) if isinstance(val, float) else val
        edges.append(ed)
    return {"nodes": nodes, "edges": edges, "quant_decimals": quant_decimals}


def size_report(graph: Graph, quant_decimals: int = 5) -> dict:
    full = json.dumps(graph.to_dict(), separators=(",", ":"))
    comp = json.dumps(compact_graph(graph, quant_decimals), separators=(",", ":"))
    return {
        "full_bytes": len(full.encode()),
        "compact_bytes": len(comp.encode()),
        "ratio": round(len(comp.encode()) / max(1, len(full.encode())), 3),
        "full_kb": round(len(full.encode()) / 1024, 1),
        "compact_kb": round(len(comp.encode()) / 1024, 1),
    }
