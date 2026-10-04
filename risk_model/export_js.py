"""Export the GBT risk model to plain JavaScript + Python<->JS parity test.

The GBT is a sum of shallow decision trees; it compiles to a self-contained JS
module with zero dependencies (nested ternaries + a sigmoid), so it runs on any
mid-range phone browser offline. We then verify PARITY: Python and JS produce
the same probability within tolerance on a fixed test set. The JS is executed
with `node` if available; otherwise the parity check is marked UNVERIFIED with
the exact command to run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile

from pipeline.synth_graph import generate
from pipeline.synth_labeler import FEATURE_COLUMNS, build_dataset
from .gbt import GradientBoostedTrees

PROC = "data/processed"
PWA_SRC = "pwa/src"


def _tree_to_js(node: dict, feat_idx: dict) -> str:
    if "leaf" in node:
        return repr(float(node["leaf"]))
    f = node["f"]
    t = node["t"]
    left = _tree_to_js(node["l"], feat_idx)
    right = _tree_to_js(node["r"], feat_idx)
    return f"(x[{f}]<={t!r}?{left}:{right})"


def export_js(model: GradientBoostedTrees, path: str) -> str:
    md = model.to_dict()
    feat_idx = {name: i for i, name in enumerate(md["feature_names"])}
    trees_js = "+\n    ".join(
        f"{md['learning_rate']!r}*{_tree_to_js(t, feat_idx)}" for t in md["trees"])
    js = f"""// AUTO-GENERATED from risk_model/export_js.py — SYNTHETIC model.
// Gradient-boosted trees for P(road impassable). Zero dependencies.
// Feature order: {md['feature_names']}
export const FEATURES = {json.dumps(md['feature_names'])};
export const BASE_SCORE = {md['base_score']!r};
function sigmoid(z) {{ return z >= 0 ? 1/(1+Math.exp(-z)) : Math.exp(z)/(1+Math.exp(z)); }}
export function predictRaw(x) {{
  return BASE_SCORE + (
    {trees_js}
  );
}}
export function predictProba(x) {{ return sigmoid(predictRaw(x)); }}
"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(js)
    return js


def parity_check(model: GradientBoostedTrees, rows, js_path: str,
                 tol: float = 1e-9) -> dict:
    X = [[float(r[c]) for c in FEATURE_COLUMNS] for r in rows[:200]]
    py = model.predict_proba(X)

    # try to run the JS with node (clearing the broken proxy preload)
    runner = f"""
import {{ predictProba }} from '{os.path.abspath(js_path)}';
const X = {json.dumps(X)};
console.log(JSON.stringify(X.map(predictProba)));
"""
    env = dict(os.environ)
    env["NODE_OPTIONS"] = ""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(runner)
        runner_path = f.name
    try:
        out = subprocess.run(["node", runner_path], capture_output=True,
                             text=True, env=env, timeout=60)
        if out.returncode != 0:
            return {"verified": False, "reason": "node failed",
                    "stderr": out.stderr[-500:],
                    "command": f"NODE_OPTIONS= node {runner_path}"}
        js = json.loads(out.stdout.strip().splitlines()[-1])
        max_abs = max(abs(a - b) for a, b in zip(py, js))
        return {"verified": max_abs <= tol, "max_abs_diff": max_abs,
                "n": len(py), "tol": tol}
    except FileNotFoundError:
        return {"verified": False, "reason": "node not found (UNVERIFIED)",
                "command": f"NODE_OPTIONS= node {runner_path}"}
    finally:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-parity", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--nx", type=int, default=20)
    args = ap.parse_args()

    g = generate(seed=1234, nx=args.nx, ny=args.nx)
    rows = build_dataset(g, seed=args.seed)
    X = [[float(r[c]) for c in FEATURE_COLUMNS] for r in rows]
    y = [int(r["label"]) for r in rows]
    model = GradientBoostedTrees(seed=args.seed).fit(X, y, FEATURE_COLUMNS)

    js_path = f"{PWA_SRC}/risk_model_SYNTHETIC.js"
    export_js(model, js_path)
    size_kb = os.path.getsize(js_path) / 1024.0
    print(f"[SYNTHETIC] exported JS model -> {js_path} ({size_kb:.1f} KB)")

    with open(f"{PROC}/risk_model_SYNTHETIC.json", "w") as f:
        json.dump(model.to_dict(), f)

    if args.check_parity:
        res = parity_check(model, rows, js_path)
        print(f"[SYNTHETIC] parity: {res}")
        with open("results/js_parity_SYNTHETIC.json", "w") as f:
            json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
