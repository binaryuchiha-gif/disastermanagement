# Architecture — ResQFlow-X

```
                         ┌─────────────────────────────────────────┐
                         │              DATA PIPELINE                │
   OSM (OSMnx) ─────────▶│  build_real_graph (UNVERIFIED)           │
   SRTM DEM   ─────────▶ │   └─ features: elev, slope, TWI,         │
   Rainfall   ─────────▶ │      flow-accum, HAND, dist-to-water      │
                         │  synth_graph + synth_labeler (SYNTHETIC) │
                         │  validate + compact (SCC, snap, quantize)│
                         └───────────────┬──────────────────────────┘
                                         │ Graph (EPSG:4326) + features
             ┌───────────────────────────┼───────────────────────────┐
             ▼                            ▼                            ▼
   ┌───────────────────┐     ┌───────────────────────┐    ┌────────────────────┐
   │   RISK MODEL (P2) │     │   ROUTING LIB (P3)     │    │   SIMULATOR (P4)    │
   │  GBT / logistic   │     │  Dijkstra, A*,         │    │  ABM, BPR congestion│
   │  spatial CV       │     │  uncertainty / UCB,    │    │  stochastic failures│
   │  isotonic + Platt │────▶│  chance-constrained,   │───▶│  shelter capacity   │
   │  split-conformal  │ p   │  Pareto, D* Lite,      │    │  reliability reports│
   │  perm importance  │fail │  MCMF + MSA, access.   │    │  stats (Wilcoxon…)  │
   └─────────┬─────────┘     └───────────┬────────────┘    └─────────┬──────────┘
             │ export_js (parity 1e-16)   │ facade.route + fail-safe  │ experiments/run_all
             ▼                            ▼                           ▼
   ┌─────────────────────────────────────────────────────────────────────────┐
   │                      PWA (P1B/P5)   —   on-device, offline                 │
   │  MapLibre GL + PMTiles (SW Range cache)   risk overlay   routes   SOS      │
   │  KD-tree snapping · turn-by-turn · off-route reroute · IndexedDB sync      │
   │  i18n (en/ta/hi) · accessibility · "why this route"                        │
   └───────────────────────────────────┬───────────────────────────────────────┘
                                        │ (online only) idempotent sync
                                        ▼
                         ┌──────────────────────────────┐
                         │   BACKEND (P5, UNVERIFIED)    │
                         │  FastAPI + SQLite + JWT       │
                         │  /sos /reports /admin /…      │
                         │  reliability scoring (tested) │
                         └──────────────────────────────┘
```

## Layering & boundaries
- **`routing/`** depends only on `routing.graph` + stdlib. No ML, no I/O. This
  keeps the algorithms unit-testable and portable to JS (`pwa/src/routing.js`).
- **`risk_model/`** depends on `pipeline` (features) + stdlib. Produces an edge
  `p_fail` field consumed by routing via `risk_model/apply.py`.
- **`pipeline/`** builds graphs + features (synthetic now, real via UNVERIFIED
  `build_real_graph`). Validation/compression are stdlib and tested.
- **`sim/`** composes routing + risk + reliability into evacuation episodes and
  computes statistics. The experiment runner is config-driven and seeded.
- **`pwa/`** re-implements the on-device subset (routing, snapping, turn-by-turn,
  model) in JS, with **parity tests** against the Python reference.
- **`backend/`** is optional/online-only; the app never gates offline routing.

## Data contract (the spine)
A single `Graph` of nodes (EPSG:4326 lat/lon, elevation, shelter flags) and
directed edges (length, speed, slope, min-elev, risk fields `p_fail/lo/hi`,
`static_risk`, capacity, accessibility flags). Everything — model, routing,
sim, PWA — reads/writes this contract, serialized as compact JSON.

## Fail-safe path
`routing/facade.route()` enforces: no model ⇒ static-risk fallback (announced);
dangerously high block probability ⇒ chance-constrained safer route (announced).
See `docs/ETHICS.md`.

## Reproducibility
`make experiments` → seeded sweep → `results/*.csv` + `manifest.json` + SVG
figures. `experiments/check_determinism` guarantees identical output per seed.
CI runs the stdlib suite + a smoke experiment + JS smoke + PY↔JS parity.
