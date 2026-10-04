# Limitations

Honest, upfront list of what this project does **not** yet establish. Nothing
here is hidden; every runnable number is on SYNTHETIC data unless stated.

## 1. Data is synthetic (the biggest limitation)
- All runnable results use a **physics-informed SYNTHETIC city graph** and a
  **synthetic flood labeler** (`pipeline/synth_graph.py`, `synth_labeler.py`),
  because the build environment had **no internet** to fetch OSM/DEM/rainfall/
  SAR flood maps. The synthetic world encodes hydrological intuition (flood low,
  flat, near-water, high-flow-accumulation edges) but is **not** a real city and
  is **not** validated against real flood extents.
- **Consequence:** H1–H4 are demonstrated *as a methodology* on synthetic data.
  They are **not** real-city findings. The paper's real-data columns are blank
  until the pipeline is run on real inputs (see `docs/REPRODUCE.md`).
- Real and synthetic labels are never mixed; every row carries `provenance`.

## 2. Synthetic labeler calibration is an assumption
Flood rates (mild ≈5%, moderate ≈7%, extreme ≈23%) and the hazard weights are
tuned by hand to be *plausible and spatially varied*, not fitted to data. The
generator's feature correlations partly drive the model's importance ranking.

## 3. Model results are nuanced, not a clean win
- Learned models **tie** the hand-tuned baseline on **ROC-AUC** (~0.76); they win
  decisively on **calibration** (ECE 0.02 vs 0.77) and **Brier** — which is what
  uncertainty-aware routing needs. Reported as such, not oversold.
- **Temporal (scenario) holdout AUC (~0.66) < spatial-CV AUC (~0.76)** and
  removing terrain features did **not** hurt the holdout — a genuine
  distribution-shift effect (train mild/moderate, test extreme). Negative result
  reported honestly in the model card.
- **Conformal intervals are wide** (radius q ≈ 0.88 on single-event synthetic
  labels). Coverage meets the ≥0.90 target, but the intervals are not yet tight
  enough to be very informative; real multi-event data should help.

## 4. Routing / simulator simplifications
- Edge failures are modeled as **independent** Bernoulli events; real flooding is
  spatially correlated. The survival-probability cost assumes independence too.
- The multi-objective Pareto method uses **ε-dominance + target bounding** for
  tractability; this is an approximation (documented accuracy tradeoff) and can
  still be the slowest method on hard long-distance pairs (hundreds of ms).
- The simulator is a custom agent-based model with a lightweight BPR congestion
  proxy, **not** a calibrated traffic simulator (SUMO integration is a stretch).
- Chance-constrained routing inside the simulator is approximated by a
  risk-averse (UCB) shelter tree; the exact CC solver lives in the routing lib.

## 5. Statistics use normal approximations
Wilcoxon/t p-values use the normal approximation (adequate for n≥30 seeds, which
we use). Not exact small-sample p-values. Multiple comparisons corrected with
Holm-Bonferroni on the headline metrics only.

## 6. On-device performance (H5) is UNVERIFIED
Desktop/sandbox latencies are real (routing sub-ms–ms; model 19 KB; PY↔JS parity
1e-16). But **phone** numbers — tile size, cold load, FPS with the risk layer,
full-network re-score ms, GPS battery — were **not** measured (no device in the
sandbox). Commands to collect them are in `docs/REPRODUCE.md`; they are the main
missing evidence for H5.

## 7. Map/PWA rendering UNVERIFIED
MapLibre+PMTiles rendering, the service-worker Range cache, the download flow,
and the Playwright offline acceptance test need `npm install` (blocked in the
sandbox). The offline *logic* (routing, snapping, turn-by-turn, sync, i18n) is
node-tested; the *rendering* is not.

## 8. Reliability scorer recall is low under sparse reporting
Precision stays ≥0.9 even against 60% adversarial reporters (never fooled), but
recall is limited when few reporters cover many blocked edges. Good conservative
behavior; incomplete coverage. Weights are hand-set, not learned.

## 9. Backend is a reference implementation
FastAPI app, JWT, SQLite, Docker are written and import-guarded but **not run**
in this environment. Auth is a minimal HMAC JWT, not a hardened production stack.
