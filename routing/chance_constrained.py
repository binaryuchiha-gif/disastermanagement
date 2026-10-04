"""Chance-constrained routing (Phase 3, item 5).

Problem: minimise expected travel time subject to a bound on the probability
the chosen path is blocked:

    min_path   sum_e time(e)
    s.t.       P(path blocked) = 1 - prod_e (1 - p_e)  <=  alpha

Both the objective (sum of times) and the block-probability surrogate
(sum of -log(1 - p_e) = -log(survival)) are ADDITIVE over edges. We relax the
constraint with a Lagrange multiplier mu >= 0:

    min_path  sum_e [ time(e) + mu * (-log(1 - p_e)) ]

For a fixed mu this is a plain shortest path (Dijkstra). As mu increases, the
optimal path's survival probability increases monotonically (it trades time for
safety), so we BISECT on mu to meet the target alpha as tightly as possible.

This gives the controllable safety/time tradeoff that H3 predicts: sweeping
alpha (equivalently mu) traces the safety-time Pareto curve.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .costs import CostConfig, CostMode
from .graph import Graph
from .shortest_path import PathResult, dijkstra, path_metrics


@dataclass
class ChanceResult:
    path: PathResult
    mu: float               # Lagrange multiplier used
    block_prob: float       # achieved P(blocked)
    time_s: float
    feasible: bool          # whether alpha was met


def _lagrangian_path(graph: Graph, source: int, target: int, mu: float) -> PathResult:
    # time + mu * survival_penalty == CostConfig(UNCERTAINTY, beta_surv=mu)
    cfg = CostConfig(mode=CostMode.UNCERTAINTY, beta_surv=mu)
    return dijkstra(graph, source, target, cfg)


def chance_constrained_route(
    graph: Graph,
    source: int,
    target: int,
    alpha: float,
    mu_hi: float = 1e5,
    iters: int = 40,
) -> ChanceResult:
    """Find the (approximately) min-time path with P(blocked) <= alpha.

    Strategy:
      1. mu=0 -> fastest path. If it already satisfies alpha, return it.
      2. Otherwise bisect mu in [0, mu_hi]. Larger mu -> safer path. Find the
         smallest mu whose path meets alpha (keeps time as low as possible).
    """
    alpha = min(max(alpha, 0.0), 1.0)

    fast = _lagrangian_path(graph, source, target, 0.0)
    if fast.is_empty:
        return ChanceResult(fast, 0.0, 1.0, math.inf, False)
    fast_block = path_metrics(graph, fast)["block_prob"]
    if fast_block <= alpha:
        return ChanceResult(fast, 0.0, fast_block, path_metrics(graph, fast)["time_s"], True)

    # safest achievable path (very large mu)
    safe = _lagrangian_path(graph, source, target, mu_hi)
    safe_block = path_metrics(graph, safe)["block_prob"]
    if safe_block > alpha:
        # even the safest path cannot meet alpha; return it, flagged infeasible
        m = path_metrics(graph, safe)
        return ChanceResult(safe, mu_hi, safe_block, m["time_s"], False)

    lo, hi = 0.0, mu_hi
    best = safe
    best_block = safe_block
    best_mu = mu_hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        p = _lagrangian_path(graph, source, target, mid)
        blk = path_metrics(graph, p)["block_prob"]
        if blk <= alpha:
            # feasible: try to go cheaper (smaller mu)
            best, best_block, best_mu = p, blk, mid
            hi = mid
        else:
            lo = mid
    m = path_metrics(graph, best)
    return ChanceResult(best, best_mu, best_block, m["time_s"], best_block <= alpha)


def safety_time_curve(
    graph: Graph,
    source: int,
    target: int,
    alphas: list[float],
) -> list[dict]:
    """Trace the safety-time curve for H3: for each alpha, the min-time feasible
    path and its achieved block probability / time."""
    out = []
    for a in alphas:
        r = chance_constrained_route(graph, source, target, a)
        out.append({
            "alpha": a,
            "achieved_block_prob": r.block_prob,
            "time_s": r.time_s,
            "feasible": r.feasible,
            "mu": r.mu,
            "n_edges": len(r.path.edges),
        })
    return out
