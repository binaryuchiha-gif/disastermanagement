"""Directed graph structures for ResQFlow-X routing.

Pure stdlib. Stores a directed (multi)graph with rich edge attributes needed by
the risk model, congestion model, and accessibility profiles.

CRS discipline: node coordinates are stored as (lat, lon) in EPSG:4326.
Distances in metres are precomputed on edges (haversine) so routing never
re-does geodesy. Web Mercator is only ever used for rendering (in the PWA),
never here.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field


@dataclass
class Node:
    id: int
    lat: float  # EPSG:4326
    lon: float
    elevation_m: float = 0.0
    is_shelter: bool = False
    shelter_capacity: int = 0
    kind: str = "junction"  # junction|shelter|hospital|high_ground|poi


@dataclass
class Edge:
    id: int
    u: int  # from node id
    v: int  # to node id
    length_m: float
    speed_kph: float = 30.0
    # risk / hazard
    p_fail: float = 0.0        # calibrated P(impassable) under current scenario
    p_fail_lo: float = 0.0     # conformal lower bound
    p_fail_hi: float = 0.0     # conformal upper bound (used by risk-averse UCB)
    static_risk: float = 0.0   # static-risk baseline score in [0,1]
    # physical / accessibility attributes
    road_class: str = "residential"
    lanes: int = 1
    oneway: bool = False
    bridge: bool = False
    tunnel: bool = False
    surface: str = "paved"
    slope_pct: float = 0.0      # grade along edge, percent
    min_elev_m: float = 0.0     # minimum elevation along edge (flood pooling)
    lit: bool = True
    has_stairs: bool = False
    # congestion
    capacity_veh_per_h: float = 600.0
    free_flow_time_s: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.free_flow_time_s <= 0.0:
            spd = max(1e-3, self.speed_kph)
            self.free_flow_time_s = self.length_m / (spd * 1000.0 / 3600.0)


class Graph:
    """Directed graph with adjacency by node id. Supports multi-edges."""

    def __init__(self) -> None:
        self.nodes: dict[int, Node] = {}
        self.edges: dict[int, Edge] = {}
        self._adj: dict[int, list[int]] = {}       # node -> outgoing edge ids
        self._radj: dict[int, list[int]] = {}      # node -> incoming edge ids

    # --- construction ---
    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        self._adj.setdefault(node.id, [])
        self._radj.setdefault(node.id, [])

    def add_edge(self, edge: Edge) -> None:
        if edge.u not in self.nodes or edge.v not in self.nodes:
            raise KeyError(f"edge {edge.id} references unknown node")
        self.edges[edge.id] = edge
        self._adj.setdefault(edge.u, []).append(edge.id)
        self._radj.setdefault(edge.v, []).append(edge.id)

    # --- queries ---
    def out_edges(self, node_id: int) -> list[Edge]:
        return [self.edges[eid] for eid in self._adj.get(node_id, ())]

    def in_edges(self, node_id: int) -> list[Edge]:
        return [self.edges[eid] for eid in self._radj.get(node_id, ())]

    def neighbors(self, node_id: int) -> list[int]:
        return [self.edges[eid].v for eid in self._adj.get(node_id, ())]

    @property
    def n_nodes(self) -> int:
        return len(self.nodes)

    @property
    def n_edges(self) -> int:
        return len(self.edges)

    # --- geodesy (haversine, metres) ---
    @staticmethod
    def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371008.8  # mean Earth radius, metres
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(min(1.0, math.sqrt(a)))

    def straight_line_m(self, a: int, b: int) -> float:
        na, nb = self.nodes[a], self.nodes[b]
        return self.haversine_m(na.lat, na.lon, nb.lat, nb.lon)

    # --- serialization (compact JSON, used for offline shipping) ---
    def to_dict(self) -> dict:
        return {
            "nodes": [vars(n) for n in self.nodes.values()],
            "edges": [vars(e) for e in self.edges.values()],
        }

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> Graph:
        g = cls()
        for nd in d["nodes"]:
            g.add_node(Node(**nd))
        for ed in d["edges"]:
            g.add_edge(Edge(**ed))
        return g

    @classmethod
    def load_json(cls, path: str) -> Graph:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
