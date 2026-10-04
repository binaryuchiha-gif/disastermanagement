"""Export shared Python<->JS routing parity vectors to results/.

Generates a SYNTHETIC graph with risk, computes Dijkstra costs for random pairs
under TIME and UNCERTAINTY modes, and writes a JSON the JS parity_check.mjs
reads. Run: python -m scripts.export_parity_vectors
"""

from __future__ import annotations

import json
import os
import random

from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph
from routing.costs import CostConfig, CostMode
from routing.shortest_path import dijkstra


def main(out="results/parity_vectors_SYNTHETIC.json", seed=99, n_cases=30):
    g = generate(seed=seed, nx=12, ny=12)
    lbl = label_graph(g, "extreme", seed=2)
    for eid, info in lbl.items():
        g.edges[eid].p_fail = info["p_true"]
        g.edges[eid].static_risk = info["p_true"]
        g.edges[eid].p_fail_hi = min(1.0, info["p_true"] + 0.1)
    shelters = [n.id for n in g.nodes.values() if n.is_shelter]
    rng = random.Random(5)
    cases = []
    for _ in range(n_cases):
        s = rng.randrange(g.n_nodes)
        t = rng.choice(shelters)
        for mode_name, cm in (("time", CostMode.TIME), ("uncertainty", CostMode.UNCERTAINTY)):
            r = dijkstra(g, s, t, CostConfig(mode=cm))
            if r.found:
                cases.append({"s": s, "t": t, "mode": mode_name, "cost": r.cost})
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"SYNTHETIC": True, "graph": g.to_dict(), "cases": cases}, f)
    print(f"[SYNTHETIC] wrote {len(cases)} parity cases -> {out}")


if __name__ == "__main__":
    main()
