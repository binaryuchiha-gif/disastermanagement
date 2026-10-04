# Viva Q&A — likely examiner questions and honest answers

### Q1. What is the actual contribution?
A pipeline + evaluation showing that **calibrated, uncertainty-aware** evacuation
routing on a city road network — driven by a learned road-failure model that
runs **fully offline on-device** — reduces mid-route failures and gives a
controllable safety/time tradeoff vs shortest-path and static-risk baselines,
and remains better than shortest-path even when the model is wrong. Backed by:
H2 (blockage reduction, Wilcoxon + large effect), H3 (safety-time curve), H4
(capacity-aware assignment), and verified on-device parity (PY↔JS 1e-16).

### Q2. Why `-log(1 - p)` as the edge penalty?
Path survival probability (assuming edge independence) is ∏(1−pₑ). Maximizing it
= minimizing Σ −log(1−pₑ), which is **additive and nonnegative**, so Dijkstra/A*
apply directly. It cleanly turns a reliability objective into a shortest-path
problem. Caveat: independence is an approximation (real floods are correlated) —
stated in LIMITATIONS.

### Q3. Why calibration, and why does H1 "tie" on AUC but you still claim a win?
Chance-constrained routing uses probabilities as *numbers*, not just rankings.
AUC only measures ranking. The hand-tuned model ranks ≈ as well (AUC ~0.76) but
is wildly miscalibrated (ECE 0.77, Brier 0.70); the learned GBT has ECE 0.02,
Brier 0.08. So H1's real content is **calibration quality**, which is what the
downstream routing needs. We report the AUC tie explicitly — we don't hide it.

### Q4. How do you avoid data leakage in CV?
**Spatial block CV**: partition the area into 0.01° blocks, assign whole blocks
to folds, so no test edge is adjacent to a same-block training edge (spatial
autocorrelation would otherwise inflate metrics). Plus a **temporal/scenario
holdout** (train mild+moderate, test extreme). The holdout AUC (0.66) is lower —
an honest distribution-shift result.

### Q5. Is A*'s heuristic admissible? Prove it.
Yes. For distance mode, `h = great-circle distance ≤ any road distance`. For
time/risk modes, `h = great-circle / v_max`, a lower bound on remaining travel
time, and all risk penalties are ≥0, so `h` never overestimates. Admissible ⇒
optimal; we also property-test `cost_A* ≥ cost_Dijkstra` across random pairs.

### Q6. Complexity of each algorithm?
See `docs/ROUTING_COMPLEXITY.md`. Dijkstra/A*/static/uncertainty: O((V+E)logV).
Chance-constrained: ×I bisection steps. Pareto: worst-case exponential, bounded
by ε-dominance + target pruning (approximation). D* Lite: O(k log k) per repair.
MCMF: O(F·(V+E)). MSA: ×N_iter MCMF.

### Q7. What is conformal prediction doing here?
Split-conformal gives distribution-free per-edge intervals [p−q, p+q] with ≈(1−α)
marginal coverage. The risk-averse (UCB) router uses the **upper** bound so it
plans against the pessimistic failure probability. Measured coverage 0.92–0.99 ≥
0.90 target. Caveat: q≈0.88 is wide on single-event synthetic labels.

### Q8. Why a custom simulator instead of SUMO?
Zero external dependencies (runs in a sealed environment), fully seed-reproducible,
and we control the stochastic-failure and model-misspecification mechanics
exactly — which is what the robustness study needs. SUMO integration is a
documented stretch comparison, not a dependency.

### Q9. How many seeds, and what statistics?
≥30 seeds per config (we use 33). Mean ± 95% CI, **paired Wilcoxon signed-rank**
(tie + continuity corrected) and paired t vs the baseline, **Cliff's delta** and
Cohen's d effect sizes, **Holm-Bonferroni** multiple-comparison correction. The
stats are stdlib and validated against textbook values in `tests/test_stats.py`.

### Q10. Biggest limitation?
The data is **synthetic** — no real OSM/DEM/flood data was ingested (no internet
in the build environment). All H1–H4 results are a *methodology demonstration* on
synthetic data, clearly tagged SYNTHETIC, not real-city findings. The exact
commands to rerun on real data are in `docs/REPRODUCE.md`. Also, phone (H5)
benchmarks are UNVERIFIED.

### Q11. What if the model is wrong in the field?
Robustness study: as model error grows 0→0.3, uncertainty-aware blockages rise
(44%→52%) but **stay below** shortest-path (57–61%). And the app has coded
**fail-safes**: no model ⇒ static-risk fallback (announced); dangerously risky
route ⇒ safer chance-constrained route (announced). See ETHICS.

### Q12. How is "offline" actually achieved?
On-device routing (JS Dijkstra, parity-verified), on-device risk model (19 KB
JS, parity 1e-16), MapLibre + a single **PMTiles** file served by a service
worker that answers **HTTP Range** requests from cache (the usual offline-maps
failure point, handled explicitly). IndexedDB queues SOS/reports for idempotent
sync when back online.

### Q13. How do you stop malicious crowd reports from closing good roads?
Transparent reliability score (agreement, proximity, model-consistency, reporter
history, recency). Simulation vs adversarial reporters: **precision stays ≥0.9
even at 60% adversarial** (never fooled into a false closure). Officials remain
in the loop; reports don't auto-close roads below threshold.

### Q14. What would you do next with real data?
Run `build_real_graph` on Chennai OSM+SRTM, label with Sentinel-1 SAR flood
extents, train LightGBM + real SHAP, re-measure H1–H4, collect phone benchmarks,
and compare against a GNN risk model (stretch) that exploits graph structure.
