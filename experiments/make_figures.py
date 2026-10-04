"""Generate publication-quality SVG figures from results/ CSVs (Phase 4).

All figures carry a 'SYNTHETIC DATA' subtitle so they can never be mistaken for
real-city findings. Pure stdlib (uses experiments.svgplot).
"""

from __future__ import annotations

import csv
import os

from experiments.svgplot import SVG

RESULTS = "results"
_SUB = "SYNTHETIC DATA — not real-city results"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fig_blocked_by_method():
    rows = _read(f"{RESULTS}/table_methods_SYNTHETIC.csv")
    scenarios = []
    methods = []
    for r in rows:
        if r["scenario"] not in scenarios:
            scenarios.append(r["scenario"])
        if r["method"] not in methods:
            methods.append(r["method"])
    svg = SVG(title="Mid-route blockages by routing method (H2)", subtitle=_SUB)
    series = []
    ymax = 0.0
    for m in methods:
        vals, errs = [], []
        for sc in scenarios:
            row = next(r for r in rows if r["scenario"] == sc and r["method"] == m)
            mean = float(row["pct_blocked_mid_mean"])
            hi = float(row["pct_blocked_mid_ci_hi"])
            vals.append(mean)
            errs.append(max(0.0, hi - mean))
            ymax = max(ymax, hi)
        series.append((m, vals, errs))
    svg.axes("rainfall scenario", "% agents blocked mid-route", 0, 1, 0, ymax * 1.15 or 1)
    svg.bars(scenarios, series)
    svg.save(f"{RESULTS}/fig_blocked_by_method_SYNTHETIC.svg")


def fig_p95_by_method():
    rows = _read(f"{RESULTS}/table_methods_SYNTHETIC.csv")
    scenarios, methods = [], []
    for r in rows:
        scenarios.append(r["scenario"]) if r["scenario"] not in scenarios else None
        methods.append(r["method"]) if r["method"] not in methods else None
    svg = SVG(title="95th-percentile evacuation time by method (H4)", subtitle=_SUB)
    series = []
    ymax = 0.0
    for m in methods:
        vals, errs = [], []
        for sc in scenarios:
            row = next(r for r in rows if r["scenario"] == sc and r["method"] == m)
            mean = float(row["p95_evac_mean"])
            hi = float(row["p95_evac_ci_hi"])
            vals.append(mean / 60.0)  # minutes
            errs.append(max(0.0, (hi - mean) / 60.0))
            ymax = max(ymax, hi / 60.0)
        series.append((m, vals, errs))
    svg.axes("rainfall scenario", "P95 evac time (min)", 0, 1, 0, ymax * 1.15 or 1)
    svg.bars(scenarios, series)
    svg.save(f"{RESULTS}/fig_p95_by_method_SYNTHETIC.svg")


def fig_safety_time():
    rows = _read(f"{RESULTS}/safety_time_SYNTHETIC.csv")
    xs = [float(r["achieved_block_prob"]) for r in rows]
    ys = [float(r["time_s"]) / 60.0 for r in rows]
    svg = SVG(title="Safety-time tradeoff curve (H3)", subtitle=_SUB)
    xmax = max(xs) * 1.1 or 1
    ymax = max(ys) * 1.1 or 1
    ymin = min(ys) * 0.9
    svg.axes("achieved P(path blocked)", "evacuation time (min)", 0, xmax, ymin, ymax)
    # sort by block prob for a clean curve
    pts = sorted(zip(xs, ys))
    svg.line([p[0] for p in pts], [p[1] for p in pts], 1, "chance-constrained")
    svg.save(f"{RESULTS}/fig_safety_time_SYNTHETIC.svg")


def fig_robustness():
    rows = _read(f"{RESULTS}/table_robustness_SYNTHETIC.csv")
    errs = [float(r["model_error"]) for r in rows]
    # find the two method columns for pct_blocked_mid
    cols = [k for k in rows[0] if k.endswith("_pct_blocked_mid")]
    svg = SVG(title="Robustness: blockages vs model error (H-robustness)", subtitle=_SUB)
    allv = [float(r[c]) for r in rows for c in cols]
    svg.axes("model error (|perturbation|)", "% blocked mid-route",
             0, max(errs) * 1.1 or 1, 0, max(allv) * 1.15 or 1)
    for i, c in enumerate(cols):
        ys = [float(r[c]) for r in rows]
        label = c.replace("_pct_blocked_mid", "")
        svg.line(errs, ys, i, label, dash=("" if i == 0 else "6,3"))
    svg.save(f"{RESULTS}/fig_robustness_SYNTHETIC.svg")


def make_all():
    os.makedirs(RESULTS, exist_ok=True)
    made = []
    for fn in (fig_blocked_by_method, fig_p95_by_method, fig_safety_time, fig_robustness):
        try:
            fn()
            made.append(fn.__name__)
        except Exception as e:  # noqa: BLE001
            print(f"[WARN] {fn.__name__} skipped: {e}")
    print(f"[SYNTHETIC] figures generated: {', '.join(made)}")


if __name__ == "__main__":
    make_all()
