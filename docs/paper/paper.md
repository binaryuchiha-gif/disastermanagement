# Uncertainty-Aware, Offline-First Evacuation Routing on a City Road Network

> **Status / honesty note.** Every quantitative result in this draft is from a
> **physics-informed SYNTHETIC** city graph and flood labeler, produced in a
> build environment with no internet access. Results are tagged **(SYNTHETIC)**
> and demonstrate the *methodology*; they are **not** real-city findings. The
> exact commands to regenerate every table/figure on real Chennai data are in
> `docs/REPRODUCE.md`; `docs/LIMITATIONS.md` lists what is unverified.

## Abstract
Flash-flood evacuation often fails not because a route is slow but because it
becomes **impassable** mid-trip, exactly when connectivity is lost. We study
whether **uncertainty-aware, risk-aware** routing — driven by a *calibrated*,
learned road-failure model running **fully offline on-device** — produces safer
evacuations than shortest-path and static-risk baselines, and how it degrades
when the model is wrong. On a synthetic city network we show that uncertainty-
aware costs cut mid-route blockages by ~78% under moderate rainfall and ~23%
under extreme rainfall (both p<0.001, large effect), that chance-constrained
routing yields a controllable safety/time curve, and that the method stays safer
than shortest-path even under substantial model error. The learned model is
dramatically better *calibrated* than a hand-tuned baseline (ECE 0.02 vs 0.77)
despite a tie on ranking (ROC-AUC ≈0.76), and compiles to a 19 KB on-device
JavaScript model that matches the Python reference to 1e-16.

## 1. Introduction
The 2015 Chennai floods displaced hundreds of thousands and showed that static
"shortest route to shelter" guidance can route people into rising water. We ask:
*does routing that explicitly reasons about the probability each road fails —
using calibrated uncertainty, computed offline on a phone — help, and is it
robust to a wrong model?* Motivation: during a flood, connectivity and power are
unreliable, so a useful tool must work on-device with no network.

## 2. Related work
Risk-aware and reliable shortest paths; chance-constrained routing; conformal
prediction for calibrated uncertainty; spatial cross-validation for geospatial ML;
flood-susceptibility mapping with terrain/hydrology features (TWI, HAND, flow
accumulation); offline vector maps (MapLibre/PMTiles). *(Citations to be added
from verified sources only; none are fabricated in this draft.)*

## 3. Problem formulation
Given a directed road graph G=(V,E) with per-edge travel time tₑ and a calibrated
failure probability pₑ (under a rainfall scenario), find routes that trade travel
time against the probability of becoming blocked. Path survival (edge-independent)
is ∏ₑ(1−pₑ); maximizing it is minimizing Σₑ −log(1−pₑ), an additive cost. We also
formulate chance-constrained routing (min time s.t. P(blocked) ≤ α), multi-
objective (time, risk, distance) routing, and capacity-constrained multi-evacuee
assignment.

## 4. Method
**Risk model (§Phase 2).** Features: elevation, slope, TWI, flow accumulation,
height-above-nearest-drainage, proximity to water, road attributes, and a
rainfall scenario variable. Model: gradient-boosted trees (logistic loss) with a
logistic-regression and hand-tuned/static baselines. Evaluation uses **spatial
block CV** and a **temporal (scenario) holdout**; probabilities are calibrated
with isotonic/Platt scaling and equipped with **split-conformal** per-edge
intervals.

**Routing (§Phase 3).** Dijkstra and A* (admissible heuristic) baselines;
uncertainty-aware cost tₑ + β·(−log(1−pₑ)) and a risk-averse UCB variant using the
conformal upper bound; chance-constrained routing via Lagrangian relaxation +
bisection; multi-objective Pareto label-setting with ε-dominance; D* Lite for
incremental rerouting; min-cost max-flow + BPR/MSA for capacity-aware assignment;
accessibility profiles.

**Simulation (§Phase 4).** An agent-based simulator samples *true* edge failures
(independently of what the model predicts), routes agents with each method under
BPR congestion and shelter capacity, and reroutes on encountering a failed edge.

**On-device (§Phase 1B).** MapLibre GL + a single PMTiles basemap cached by a
service worker that answers HTTP Range requests offline; the risk model and
router are ported to dependency-free JavaScript with parity tests.

## 5. Implementation
Pure-Python-stdlib research core (routing, simulator, statistics, the GBT, and
calibration/conformal) so it is dependency-free and fully reproducible; a JS port
for the phone; a FastAPI backend for optional online sync. 67 automated tests;
CI runs the suite, a seeded smoke experiment, a determinism check, and the Python↔
JS parity checks.

## 6. Experiments & Results (SYNTHETIC)

### 6.1 H1 — learned vs baseline risk (spatial CV)
| Model | ROC-AUC | Brier | ECE |
|-------|--------:|------:|----:|
| legacy hand-tuned | 0.763 | 0.700 | 0.773 |
| static risk | 0.700 | 0.180 | 0.272 |
| logistic (learned) | 0.766 | 0.085 | 0.038 |
| **GBT (learned)** | **0.776** | **0.080** | **0.019** |

Learned models **tie on ranking** (AUC ≈0.76–0.78) but are vastly better
**calibrated** (GBT ECE 0.019 vs hand-tuned 0.773). Since uncertainty-aware
routing consumes probabilities, calibration is the operative quantity → **H1
supported for calibration/probability quality** (reported honestly as an
AUC tie). Isotonic calibration improves held-out ECE 0.203→0.153; split-conformal
coverage **0.99 ≥ 0.90** target (interval radius q≈0.88 is wide — a limitation).
Permutation importance ranks flow-accumulation, TWI, and low elevation highest —
consistent with hydrology.

### 6.2 H2 — mid-route blockages (33 seeds, paired Wilcoxon vs shortest-distance)
| Scenario | shortest-dist | static-risk | uncertainty | p (unc) | effect |
|----------|-------------:|-----------:|-----------:|--------:|:------:|
| mild | 1.50% | 0.22% | **0.22%** | 0.004 | medium |
| moderate | 12.56% | 2.73% | **2.80%** | <0.001 | large (δ=−0.96) |
| extreme | 57.0% | 45.1% | **44.1%** | <0.001 | large (δ=−0.56) |

Uncertainty-aware routing reduces mid-route blockages at every intensity, with
large effect sizes under moderate/extreme rain; reroutes fall from 644→269
(extreme). **H2 supported (SYNTHETIC).** Static-risk and uncertainty are close
here because, with a *perfect* model and rerouting, both avoid the worst edges;
their difference is sharper under model error (§6.4) and in reroute count.

### 6.3 H3 — safety/time tradeoff (chance-constrained)
As α tightens 0.9→0.1, achieved P(blocked) falls monotonically **0.62→0.17**
while evacuation time rises **555 s→822 s**, saturating at the safest achievable
route. A controllable, monotone safety-time curve → **H3 supported (SYNTHETIC).**
(Figure: `results/fig_safety_time_SYNTHETIC.svg`.)

### 6.4 Robustness — wrong model (extreme rainfall)
| model error | uncertainty blocked | shortest-dist blocked |
|------------:|--------------------:|----------------------:|
| 0.0 | 44.1% | 57.0% |
| 0.1 | 48.4% | 60.8% |
| 0.2 | 50.0% | 60.8% |
| 0.3 | 52.4% | 60.8% |

Uncertainty-aware routing degrades gracefully and **stays below** shortest-path
even at error 0.3. Honest result: the gap narrows as the model worsens, as
expected.

### 6.5 H4 — capacity & congestion
Capacity-aware min-cost max-flow assignment respects shelter capacities by
construction (property-tested); MSA adds BPR congestion. Full tail-time/overload
tables regenerate via `make experiments`. (On synthetic shelters the overload
metric is available in `SimResult`.)

### 6.6 H5 — on-device
The GBT exports to **19 KB** JS; Python↔JS **model** parity max-diff **1.4e-16**;
Python↔JS **routing** parity max-diff **0** over 60 cases. Desktop routing is tens
of ms on a 2k-node graph. **Phone latency/FPS/battery are UNVERIFIED** (no device
in the build environment) — see `docs/REPRODUCE.md`.

## 7. Ablations
Feature-group ablation (temporal holdout): removing terrain features did not
reduce holdout AUC (slight rise), and holdout AUC (0.66) < spatial-CV AUC (0.78)
— a genuine distribution-shift effect, reported rather than hidden.

## 8. Limitations
Synthetic data; independence assumption for edge failures; wide conformal
intervals; Pareto latency; custom (not calibrated) simulator; phone benchmarks
unverified. Full list in `docs/LIMITATIONS.md`.

## 9. Ethics
Life-critical disclaimers, coded fail-safes (conservative fallback when the model
is unavailable or the route is too risky, both announced to the user), human-in-
the-loop for officials, data minimization. See `docs/ETHICS.md`.

## 10. Future work
Real Chennai data (OSM+SRTM+SAR flood maps); GNN risk model exploiting graph
structure; time-dependent routing with flood propagation; online Bayesian risk
updates from live reports; a 2015 digital-twin replay; evacuation-trigger timing.

## Contribution statement
1. **Calibrated offline risk model** that beats a hand-tuned baseline on
   calibration (ECE 0.02 vs 0.77) and ports to a 19 KB on-device model with
   1e-16 parity. *(Table §6.1; `results/model_eval_SYNTHETIC.json`.)*
2. **Uncertainty-aware routing reduces mid-route failures** with large effect
   sizes under moderate/extreme rainfall. *(Table §6.2; `fig_blocked_by_method_SYNTHETIC.svg`.)*
3. **A controllable safety/time tradeoff** via chance-constrained routing.
   *(§6.3; `fig_safety_time_SYNTHETIC.svg`.)*
4. **Graceful degradation under model error**, staying safer than shortest-path.
   *(§6.4; `fig_robustness_SYNTHETIC.svg`.)*
