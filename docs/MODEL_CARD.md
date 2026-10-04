# Model Card — ResQFlow-X road-failure risk model

> ⚠️ The numbers in this card are from **SYNTHETIC data** (physics-informed
> labeler), produced in a no-internet sandbox. They demonstrate the pipeline and
> the H1 methodology; they are **not real-city results**. Rerun `train_lib.py`
> on real inputs to populate the REAL columns (see `docs/REPRODUCE.md`).

## Model details
- **Task:** binary classification — predict P(road segment impassable /
  flooded) under a rainfall scenario.
- **Headline model:** gradient-boosted regression trees (GBT), logistic loss,
  from-scratch pure-stdlib implementation (`risk_model/gbt.py`); histogram-based
  split finding. Defaults: 60 trees, depth 3, lr 0.2, subsample 0.8, seed-fixed.
- **Baselines:** hand-tuned legacy logistic (`legacy/`), static-risk rule,
  learned logistic regression.
- **Library variants (UNVERIFIED):** LightGBM, RandomForest, calibrated via
  sklearn `CalibratedClassifierCV`, real SHAP (`risk_model/train_lib.py`).

## Features (9)
`inv_elev_norm, inv_slope_norm, twi_norm, flow_acc_norm, near_water_norm,
hand_norm (height-above-nearest-drainage), bridge_flag, road_primary, rain_norm`.
Terrain/hydrology features are derived from the DEM/graph (`pipeline/features.py`);
`rain_norm` is the scenario variable.

## Evaluation protocol
- **Spatial block cross-validation** (5 folds, 0.01° blocks) so no test edge is
  adjacent to a same-block training edge — mitigates spatial autocorrelation
  leakage.
- **Temporal (scenario) holdout:** train on mild+moderate, test on extreme
  (emulates event holdout).
- Metrics: ROC-AUC, PR-AUC, F1@tuned-threshold, Brier, log loss, ECE.
- Calibration: Platt + isotonic on a held-out split; split-conformal intervals.

## Results (SYNTHETIC, spatial CV, seed 0, nx=25 → 6762 rows, 834 positive)
| Model | ROC-AUC | PR-AUC | Brier | ECE |
|-------|--------:|-------:|------:|----:|
| legacy hand-tuned | 0.774 | 0.500 | 0.699 | 0.772 |
| static risk | 0.718 | 0.319 | 0.178 | 0.271 |
| logistic (learned) | 0.773 | 0.502 | 0.085 | 0.041 |
| **GBT (learned)** | 0.763 | **0.507** | **0.082** | **0.020** |

**H1 interpretation (honest):** on *ranking* (ROC-AUC) the learned models tie
the hand-tuned baseline (~0.76–0.77). On the *probabilistic* metrics that
uncertainty-aware routing actually depends on — **Brier and ECE** — the learned
models are dramatically better (GBT ECE 0.020 vs hand-tuned 0.772). The
hand-tuned model ranks acceptably but is grossly mis-calibrated, so its
"probabilities" are unusable for chance-constrained routing. **H1 is supported
for calibration/probability quality; it is a tie on pure ranking** — reported as
such.

## Calibration & uncertainty
- ECE improves with isotonic: 0.208 → 0.165 (held-out test).
- **Split-conformal (α=0.1):** empirical coverage **0.918 ≥ 0.90** target ✓.
  Caveat: the conformal radius `q ≈ 0.86` is large (wide intervals) because the
  single-event SYNTHETIC labels are noisy; on real multi-event data the
  intervals should tighten. Recorded in `docs/LIMITATIONS.md`.

## Explainability (permutation importance, GBT)
Top features: **flow_acc_norm > twi_norm > inv_elev_norm > hand_norm**. This
matches hydrological intuition (flood where water accumulates, where the wetness
index is high, and at low elevation / low height-above-drainage) — the sanity
check the design requires. `near_water_norm` and `inv_slope_norm` showed
near-zero/slightly-negative permutation importance on SYNTHETIC data (documented
as a limitation of the synthetic generator's feature correlations).

## Ablations (ROC-AUC, temporal holdout on extreme)
Removing terrain features did **not** reduce AUC on the temporal holdout (it
slightly rose, −0.03 "drop"), and holdout AUC (0.66) < spatial-CV AUC (0.76).
This is an honest distribution-shift effect: training on mild/moderate (few
positives) and testing on extreme is genuinely hard. Reported as a negative/
nuanced result, not hidden.

## On-device deployment
- GBT exported to dependency-free JS (`risk_model/export_js.py`), **18.8 KB**.
- **Python↔JS parity VERIFIED**: max abs diff **1.67e-16** over 200 samples
  (`results/js_parity_SYNTHETIC.json`), executed with `node`.
- Per-full-network re-score latency on a mid-range **phone**: **UNVERIFIED** —
  must be measured with the PWA harness (`docs/REPRODUCE.md`).

## Intended use & limitations
Research/educational decision support only. Not a certified emergency tool.
Predictions can be wrong, especially out-of-distribution (new rainfall regimes,
unseen areas). The system falls back to conservative routing when the model is
unavailable or low-confidence. See `docs/ETHICS.md` and `docs/LIMITATIONS.md`.
