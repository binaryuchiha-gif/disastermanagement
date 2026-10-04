"""Determinism check (used in CI): running one episode twice with the same seed
must produce byte-identical outcome hashes. Guards the 'all randomness seeded'
rule."""

from __future__ import annotations

import argparse
import hashlib
import json

from pipeline.synth_graph import generate
from pipeline.synth_labeler import label_graph
from sim.simulator import SimConfig, simulate


def _episode_hash(seed: int) -> str:
    g = generate(seed=1234, nx=15, ny=15)
    lbl = label_graph(g, "extreme", seed=seed)
    true_pfail = {eid: info["p_true"] for eid, info in lbl.items()}
    import random
    rng = random.Random(seed + 999)
    nonsh = [n.id for n in g.nodes.values() if not n.is_shelter]
    origins = rng.sample(nonsh, 25)
    res = simulate(g, origins, true_pfail, dict(true_pfail),
                   SimConfig(n_agents=60, seed=seed, method="uncertainty"))
    payload = [(o.agent_id, o.reached_shelter, round(o.evac_time_s, 3),
                o.blocked_midroute, o.n_reroutes, o.failed) for o in res.outcomes]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()
    h1 = _episode_hash(args.seed)
    h2 = _episode_hash(args.seed)
    assert h1 == h2, f"NON-DETERMINISTIC: {h1} != {h2}"
    print(f"[OK] deterministic (seed={args.seed}): {h1[:16]}")


if __name__ == "__main__":
    main()
