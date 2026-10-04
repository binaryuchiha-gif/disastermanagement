"""High-level routing facade: one entry point the simulator, backend, and PWA
share, plus the fail-safe fallback logic required by Phase 6 / ETHICS.

`route()` dispatches to the right algorithm by method name and applies the
fail-safe rule: if the risk model is unavailable or the chosen path is
low-confidence (wide conformal interval / high block probability), it falls
back to a conservative route and reports that it did so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .chance_constrained import chance_constrained_route
from .costs import AccessibilityProfile, CostConfig, CostMode
from .graph import Graph
from .pareto import pareto_routes, select_topsis, select_by_weights
from .shortest_path import PathResult, astar, dijkstra, path_metrics

METHODS = [
    "shortest_distance",   # 1
    "astar_time",          # 2
    "static_risk",         # 3
    "uncertainty",         # 4a
    "uncertainty_ucb",     # 4b
    "chance_constrained",  # 5
    "pareto_topsis",       # 6
    "accessibility",       # 9
]


@dataclass
class RouteResponse:
    method: str
    path: PathResult
    metrics: dict
    fail_safe_triggered: bool = False
    fail_safe_reason: str = ""
    explanation: dict = field(default_factory=dict)


def route(
    graph: Graph,
    source: int,
    target: int,
    method: str = "uncertainty",
    alpha: float = 0.1,
    weights: tuple[float, float, float] = (1.0, 1.0, 1.0),
    profile: AccessibilityProfile | None = None,
    model_available: bool = True,
    low_confidence_block_threshold: float = 0.8,
) -> RouteResponse:
    """Compute a route by method, with fail-safe fallback."""
    # Fail-safe #1: no model -> conservative static-risk routing, announced.
    if not model_available and method in ("uncertainty", "uncertainty_ucb",
                                          "chance_constrained"):
        res = dijkstra(graph, source, target, CostConfig(mode=CostMode.STATIC_RISK))
        return RouteResponse("static_risk(fallback)", res, path_metrics(graph, res),
                             True, "risk model unavailable; using static-risk fallback")

    if method == "shortest_distance":
        res = dijkstra(graph, source, target, CostConfig(mode=CostMode.DISTANCE))
    elif method == "astar_time":
        res = astar(graph, source, target, CostConfig(mode=CostMode.TIME))
    elif method == "static_risk":
        res = dijkstra(graph, source, target, CostConfig(mode=CostMode.STATIC_RISK))
    elif method == "uncertainty":
        res = dijkstra(graph, source, target, CostConfig(mode=CostMode.UNCERTAINTY))
    elif method == "uncertainty_ucb":
        res = dijkstra(graph, source, target, CostConfig(mode=CostMode.UNCERTAINTY_UCB))
    elif method == "chance_constrained":
        cc = chance_constrained_route(graph, source, target, alpha)
        res = cc.path
    elif method == "pareto_topsis":
        front = pareto_routes(graph, source, target)
        pick = select_by_weights(front, *weights) if weights != (1, 1, 1) \
            else select_topsis(front)
        res = _pareto_to_pathresult(pick)
    elif method == "accessibility":
        res = dijkstra(graph, source, target,
                       CostConfig(mode=CostMode.ACCESSIBILITY,
                                  profile=profile or AccessibilityProfile.pedestrian()))
    else:
        raise ValueError(f"unknown method {method}")

    metrics = path_metrics(graph, res)
    resp = RouteResponse(method, res, metrics)

    # Fail-safe #2: route is dangerously high block probability -> try safest and warn.
    if res.found and metrics["block_prob"] > low_confidence_block_threshold \
            and method != "chance_constrained":
        safe = chance_constrained_route(graph, source, target, alpha=0.3)
        safe_m = path_metrics(graph, safe.path)
        if safe.path.found and safe_m["block_prob"] < metrics["block_prob"]:
            resp = RouteResponse("chance_constrained(fallback)", safe.path, safe_m,
                                 True,
                                 f"primary route block prob {metrics['block_prob']:.2f} "
                                 f"exceeded {low_confidence_block_threshold}; "
                                 f"switched to safer route")
    resp.explanation = explain_route(graph, resp.path)
    return resp


def _pareto_to_pathresult(p) -> PathResult:
    if p is None:
        return PathResult([], [], float("inf"), False)
    return PathResult(p.nodes, p.edges, p.time_s, True)


def explain_route(graph: Graph, res: PathResult) -> dict:
    """'Why this route?' panel: top contributing risk factors along the path."""
    if res.is_empty:
        return {}
    riskiest = sorted(
        (graph.edges[eid] for eid in res.edges),
        key=lambda e: e.p_fail, reverse=True,
    )[:3]
    return {
        "n_edges": len(res.edges),
        "mean_edge_pfail": sum(graph.edges[e].p_fail for e in res.edges) / max(1, len(res.edges)),
        "riskiest_segments": [
            {"edge_id": e.id, "p_fail": round(e.p_fail, 3),
             "road_class": e.road_class, "min_elev_m": round(e.min_elev_m, 1),
             "bridge": e.bridge}
            for e in riskiest
        ],
    }
