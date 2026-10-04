"""SYNTHETIC city-graph generator (physics-informed, seeded, pure stdlib).

Produces a grid-plus-random road network with a plausible terrain field so that
the hydrology-based synthetic labeler has something physically meaningful to act
on. This is a clearly-labelled substitute for the real OSM/DEM graph; every
artifact it emits is tagged SYNTHETIC.

Design choices (documented for the viva):
  * A regular lattice gives predictable connectivity and makes property tests
    tractable; we add diagonal/long "arterial" shortcuts and random edge
    removals so the graph is not trivially symmetric.
  * Terrain is a smooth synthetic elevation surface (sum of a tilted plane and a
    few Gaussian bumps) plus a "river" low-corridor, so elevation, slope, flow
    accumulation and distance-to-water are internally consistent -- the labeler
    then floods low, flat, near-river edges, matching hydrological intuition.
  * Everything is a deterministic function of the seed.

Coordinates are synthetic lat/lon around a placeholder origin; they are NOT a
real place and must never be presented as Chennai geometry.
"""

from __future__ import annotations

import argparse
import json
import math
import random

from routing.graph import Edge, Graph, Node

# placeholder origin (clearly not claimed to be real-city geometry)
_ORIGIN_LAT = 12.95
_ORIGIN_LON = 80.20
_DEG_PER_CELL = 0.0025  # ~250-280 m spacing


def _elevation(x: float, y: float, nx: int, ny: int, rng: random.Random,
               bumps: list[tuple[float, float, float, float]]) -> float:
    """Smooth synthetic elevation surface in metres."""
    # tilted plane: higher in the NW, lower toward SE (toward the "sea")
    base = 2.0 + 0.9 * (nx - x) + 0.6 * (ny - y)
    # a river low-corridor along a diagonal: subtract a trough
    river = 6.0 * math.exp(-((x - y) ** 2) / (2 * (nx * 0.12) ** 2))
    bump_sum = 0.0
    for bx, by, amp, sig in bumps:
        bump_sum += amp * math.exp(-(((x - bx) ** 2 + (y - by) ** 2) / (2 * sig ** 2)))
    return max(0.0, base - river + bump_sum)


def generate(seed: int = 1234, nx: int = 40, ny: int = 40,
             drop_prob: float = 0.08, arterial_prob: float = 0.04) -> Graph:
    """Generate a SYNTHETIC directed city graph with ~nx*ny nodes.

    Default 40x40 = 1600 nodes, ~ up to ~6000 directed edges (within the
    2k-20k node target band when scaled up; kept modest for fast CI)."""
    rng = random.Random(seed)
    g = Graph()

    bumps = [(rng.uniform(0, nx), rng.uniform(0, ny), rng.uniform(1.5, 5.0),
              rng.uniform(2.0, 6.0)) for _ in range(5)]

    def nid(i: int, j: int) -> int:
        return i * ny + j

    # nodes
    elev = {}
    for i in range(nx):
        for j in range(ny):
            e = _elevation(i, j, nx, ny, rng, bumps)
            elev[(i, j)] = e
            lat = _ORIGIN_LAT + j * _DEG_PER_CELL
            lon = _ORIGIN_LON + i * _DEG_PER_CELL
            g.add_node(Node(id=nid(i, j), lat=lat, lon=lon, elevation_m=e))

    eid = 0

    def add_bidir(a: int, b: int, road_class: str, speed: float, lanes: int,
                  cap: float) -> None:
        nonlocal eid
        na, nb = g.nodes[a], g.nodes[b]
        length = Graph.haversine_m(na.lat, na.lon, nb.lat, nb.lon)
        dz = nb.elevation_m - na.elevation_m
        slope = 100.0 * dz / max(length, 1e-6)
        min_e = min(na.elevation_m, nb.elevation_m)
        bridge = min_e < 1.5 and rng.random() < 0.3
        for (u, v, s) in ((a, b, slope), (b, a, -slope)):
            g.add_edge(Edge(id=eid, u=u, v=v, length_m=length, speed_kph=speed,
                            road_class=road_class, lanes=lanes,
                            slope_pct=s, min_elev_m=min_e, bridge=bridge,
                            capacity_veh_per_h=cap,
                            lit=(road_class != "residential") or rng.random() > 0.3,
                            has_stairs=False))
            eid += 1

    # lattice edges with random drops
    for i in range(nx):
        for j in range(ny):
            if i + 1 < nx and rng.random() > drop_prob:
                add_bidir(nid(i, j), nid(i + 1, j), "residential", 30, 1, 600)
            if j + 1 < ny and rng.random() > drop_prob:
                add_bidir(nid(i, j), nid(i, j + 1), "residential", 30, 1, 600)

    # arterials: long fast shortcuts across several cells
    for _ in range(int(arterial_prob * nx * ny)):
        i = rng.randrange(nx)
        j = rng.randrange(ny)
        di = rng.choice([-3, -2, 2, 3])
        dj = rng.choice([-3, -2, 2, 3])
        i2, j2 = i + di, j + dj
        if 0 <= i2 < nx and 0 <= j2 < ny:
            add_bidir(nid(i, j), nid(i2, j2), "primary", 50, 2, 1500)

    # designate some high-ground nodes as shelters (highest elevation quantile)
    nodes_by_elev = sorted(g.nodes.values(), key=lambda n: n.elevation_m, reverse=True)
    n_shelters = max(3, (nx * ny) // 200)
    cap_total = int(nx * ny * 2.0)
    for k, node in enumerate(nodes_by_elev[:n_shelters]):
        node.is_shelter = True
        node.kind = "shelter"
        node.shelter_capacity = max(50, cap_total // n_shelters)

    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate SYNTHETIC city graph")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--nx", type=int, default=40)
    ap.add_argument("--ny", type=int, default=40)
    ap.add_argument("--out", default="data/processed/synthetic_city.json")
    args = ap.parse_args()
    g = generate(seed=args.seed, nx=args.nx, ny=args.ny)
    g.save_json(args.out)
    meta = {
        "SYNTHETIC": True,
        "seed": args.seed,
        "n_nodes": g.n_nodes,
        "n_edges": g.n_edges,
        "note": "SYNTHETIC physics-informed city graph. NOT a real place.",
    }
    with open(args.out.replace(".json", ".meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[SYNTHETIC] graph: {g.n_nodes} nodes, {g.n_edges} edges -> {args.out}")


if __name__ == "__main__":
    main()
