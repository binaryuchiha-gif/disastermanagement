"""Runtime/memory benchmarks for the routing algorithms (Phase 3).

Reports wall-clock latency and peak memory (via tracemalloc) for each algorithm
on SYNTHETIC graphs of increasing size. Pure stdlib. Deterministic (seeded).

Usage:
    python -m routing.benchmark --sizes 15 25 35 --repeats 5 --out results/bench_routing_SYNTHETIC.csv

NOTE: These are DESKTOP/sandbox numbers. On-device (mid-range Android) numbers
for H5 must be collected separately with the PWA harness (see docs/REPRODUCE.md);
they are marked UNVERIFIED until you run them.
"""

from __future__ import annotations

import argparse
import time
import tracemalloc

from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph
from routing.chance_constrained import chance_constrained_route
from routing.costs import CostConfig, CostMode
from routing.dynamic import DStarLite, full_recompute
from routing.pareto import pareto_routes
from routing.shortest_path import astar, dijkstra


def _prep(nx: int, seed: int = 1234):
    g = generate(seed=seed, nx=nx, ny=nx)
    lbl = label_graph(g, "extreme", seed=1)
    for eid, info in lbl.items():
        g.edges[eid].p_fail = info["p_true"]
        g.edges[eid].static_risk = info["p_true"]
        g.edges[eid].p_fail_hi = min(1.0, info["p_true"] + 0.1)
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    return g, shelters


def _time_ms(fn, repeats: int) -> tuple[float, float]:
    """Return (median_ms, peak_kb) over `repeats` runs."""
    times = []
    tracemalloc.start()
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    times.sort()
    return times[len(times) // 2], peak / 1024.0


def run(sizes: list[int], repeats: int) -> list[dict]:
    rows = []
    for nx in sizes:
        g, shelters = _prep(nx)
        s, t = 0, shelters[0]
        algos = {
            "dijkstra_time": lambda: dijkstra(g, s, t, CostConfig(mode=CostMode.TIME)),
            "astar_time": lambda: astar(g, s, t, CostConfig(mode=CostMode.TIME)),
            "dijkstra_uncertainty": lambda: dijkstra(g, s, t, CostConfig(mode=CostMode.UNCERTAINTY)),
            "chance_constrained": lambda: chance_constrained_route(g, s, t, 0.1),
            "pareto": lambda: pareto_routes(g, s, t),
            "dstar_lite_build": lambda: DStarLite(g, s, t, CostConfig(mode=CostMode.TIME)),
            "full_recompute": lambda: full_recompute(g, s, t, CostConfig(mode=CostMode.TIME), set()),
        }
        for name, fn in algos.items():
            med, peak = _time_ms(fn, repeats)
            rows.append({
                "algorithm": name, "n_nodes": g.n_nodes, "n_edges": g.n_edges,
                "median_ms": round(med, 3), "peak_kb": round(peak, 1),
                "SYNTHETIC": True,
            })
            print(f"[SYNTHETIC] {name:24s} n={g.n_nodes:5d} "
                  f"m={g.n_edges:5d}  {med:8.3f} ms  {peak/1024:7.1f} KB")
    return rows


def dstar_vs_recompute(nx: int = 30, n_blocks: int = 10, seed: int = 1234) -> list[dict]:
    """Compare incremental D* Lite repair latency vs full recompute as edges are
    blocked one by one along the current route."""
    g, shelters = _prep(nx, seed)
    s, t = 0, shelters[0]
    cfg = CostConfig(mode=CostMode.TIME)
    ds = DStarLite(g, s, t, cfg)
    path = ds.extract_path()
    rows = []
    blocked: set[int] = set()
    for i in range(min(n_blocks, len(path.edges))):
        eid = path.edges[min(i, len(path.edges) - 1)]
        blocked.add(eid)

        t0 = time.perf_counter()
        ds.update_edge_blocked(eid)
        _ = ds.extract_path()
        ds_ms = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        _ = full_recompute(g, s, t, cfg, blocked)
        fr_ms = (time.perf_counter() - t0) * 1000.0

        rows.append({"event": i + 1, "dstar_lite_ms": round(ds_ms, 3),
                     "full_recompute_ms": round(fr_ms, 3), "SYNTHETIC": True})
        path = ds.extract_path()
        if not path.found:
            break
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[15, 25, 35])
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default="results/bench_routing_SYNTHETIC.csv")
    args = ap.parse_args()
    rows = run(args.sizes, args.repeats)
    import csv
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[SYNTHETIC] wrote {args.out}")


if __name__ == "__main__":
    main()
