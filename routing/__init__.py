"""ResQFlow-X routing library (pure Python standard library).

Implements the Phase 3 algorithms:
  1. Dijkstra (shortest distance / time) - baseline
  2. A* with admissible heuristic
  3. Static risk-weighted cost - baseline
  4. Uncertainty-aware routing (survival-probability cost; UCB variant)
  5. Chance-constrained routing (Lagrangian relaxation + sweep)
  6. Multi-objective Pareto routing (label-setting)
  7. Dynamic rerouting (D* Lite vs full recompute)
  8. Multi-evacuee assignment (min-cost max-flow + BPR congestion via MSA)
  9. Accessibility-profile routing

All algorithms share the Graph structure and EdgeCost model in `graph.py`
and `costs.py`, and share test vectors with the JS/WASM port.
"""

from .graph import Edge, Graph, Node  # noqa: F401
