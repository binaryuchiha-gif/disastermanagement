# Performance Budget

Two columns: **measured (desktop/sandbox, REAL numbers on SYNTHETIC graphs)** and
**phone target / UNVERIFIED** (must be collected on a mid-range Android device —
see `docs/REPRODUCE.md` §B7). Nothing here is fabricated.

## Routing latency (SYNTHETIC graphs, worst-case far cross-city query)
From `results/bench_routing_SYNTHETIC.csv` (`routing.benchmark`, far source →
nearest shelter; this is the *stressful* case — near-source queries are
sub-millisecond). Median of repeated runs.

| Algorithm | 400 nodes | 900 nodes | 2025 nodes | Phone target |
|-----------|----------:|----------:|-----------:|-------------:|
| Dijkstra (time) | 4.1 ms | 9.4 ms | 25.6 ms | < 150 ms (UNVERIFIED) |
| A* (time) | 7.8 ms | 20.4 ms | 57.1 ms | < 150 ms (UNVERIFIED) |
| Dijkstra (uncertainty) | 9.4 ms | 23.7 ms | 52.8 ms | < 200 ms (UNVERIFIED) |
| Chance-constrained | 15.0 ms | 36.4 ms | 87.8 ms | < 400 ms (UNVERIFIED) |
| Pareto (ε-dom, budget 20k) | 7.1 s | 6.7 s | 6.6 s | desktop-only ⚠️ |
| D* Lite (build once) | 94 ms | 392 ms | 1.82 s | amortized over repairs |
| Full recompute | 3.8 ms | 10.4 ms | 26.1 ms | < 150 ms (UNVERIFIED) |

> **Takeaways / honest caveats.**
> - Shortest-path & uncertainty-aware routing are tens of ms even on a 2k-node
>   graph on desktop — comfortably within an interactive budget; phone will be
>   slower (pure-JS port) but these are small graphs.
> - **Pareto is the bottleneck** (seconds) — reserved for the desktop
>   route-comparison view, not on-device. On-device "balanced" routing should use
>   the chance-constrained method. (Limitation recorded in `docs/LIMITATIONS.md`.)
> - D* Lite's build cost is paid once; it wins only when many localized repairs
>   follow. For a single reroute, full recompute is cheaper here.

## Risk model (SYNTHETIC)
| Metric | Measured | Phone target |
|--------|---------:|-------------:|
| Model size (JS) | **19.2 KB** | < 200 KB ✓ |
| Python↔JS parity (max abs diff) | **1.4e-16** | ≤ 1e-9 ✓ |
| Full-network re-score (all edges), desktop | measured via `scoreEdges` in Vitest/node | — |
| Full-network re-score, **phone** | **UNVERIFIED** | < 500 ms |

## Data / storage
| Artifact | Measured | Target |
|----------|---------:|-------:|
| Graph JSON (synthetic 45×45) | 3112 KB | — |
| Compact graph (quantized) | **700 KB (0.225×)** | — |
| PMTiles basemap (study area) | **UNVERIFIED** (build via `scripts/build_tiles.sh`) | tens of MB |

## PWA runtime (phone, all UNVERIFIED — collect per REPRODUCE §B7)
| Metric | Target |
|--------|-------:|
| Cold load time (airplane mode, from cache) | < 3 s |
| FPS with full risk layer (zoom 12–14, panning) | ≥ 30 FPS |
| Route latency (shown in "why this route" panel) | < 300 ms |
| GPS battery impact (15-min tracked session) | documented, minimized |

## How to refresh these numbers
Desktop/synthetic: `python -m routing.benchmark …`, `python -m risk_model.export_js --check-parity`, `python -c "from pipeline.validate import size_report; …"`.
Phone: `docs/REPRODUCE.md` §B7.
