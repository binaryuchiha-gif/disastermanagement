"""ResQFlow-X risk model (Phase 2).

Predict P(road segment impassable) under a rainfall scenario.

The runnable core is PURE STDLIB (no numpy/sklearn/lightgbm):
  * logistic.py     - logistic regression (gradient descent), a learned baseline
  * gbt.py          - a compact gradient-boosted regression-tree ensemble for
                      probability prediction (the headline learned model here)
  * calibration.py  - Platt & isotonic calibration
  * conformal.py    - split-conformal prediction intervals per edge
  * metrics.py      - ROC-AUC, PR-AUC, F1, Brier, log-loss, ECE, calibration bins
  * spatial_cv.py   - spatial block cross-validation (no neighbour leakage)
  * importance.py   - permutation importance (SHAP-style attribution)
  * train.py        - orchestrates training + evaluation on SYNTHETIC data,
                      writes model card inputs and a JS-exportable model
  * export_js.py    - exports the GBT to plain JS + Python<->JS parity check

The library-backed variants (LightGBM/XGBoost/RandomForest + real SHAP + MLflow)
are written in train_lib.py and marked UNVERIFIED (need `pip install`).
"""
