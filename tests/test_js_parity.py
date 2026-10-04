"""Python<->JS parity test for the exported risk model.

Skipped (not failed) if `node` is unavailable, so the stdlib suite stays green
everywhere; where node exists (CI, this sandbox) it genuinely verifies parity.
"""

from __future__ import annotations

import shutil

import pytest

from pipeline.synth_graph import generate
from pipeline.synth_labeler import FEATURE_COLUMNS, build_dataset
from risk_model.export_js import export_js, parity_check
from risk_model.gbt import GradientBoostedTrees


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_python_js_parity(tmp_path):
    g = generate(seed=1234, nx=16, ny=16)
    rows = build_dataset(g, seed=0)
    X = [[float(r[c]) for c in FEATURE_COLUMNS] for r in rows]
    y = [int(r["label"]) for r in rows]
    model = GradientBoostedTrees(n_estimators=30, seed=0).fit(X, y, FEATURE_COLUMNS)
    js_path = tmp_path / "model.mjs"
    export_js(model, str(js_path))
    res = parity_check(model, rows, str(js_path), tol=1e-9)
    if not res.get("verified") and res.get("reason", "").startswith("node"):
        pytest.skip(f"node parity could not run: {res}")
    assert res["verified"], f"parity failed: {res}"
    assert res["max_abs_diff"] <= 1e-9
