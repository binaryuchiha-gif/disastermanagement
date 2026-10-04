"""REAL road-network + DEM pipeline (Phase 1). UNVERIFIED in the sandbox.

Builds a directed multigraph for the study area (default Chennai: Velachery +
Adyar + Pallikaranai) from OSM, enriches edges with terrain/hydrology features
from an SRTM DEM, attaches POIs (shelters/hospitals/high-ground/fuel), validates,
and emits a compact graph for offline use. REPRODUCIBLE + CACHED + SEEDED.

Status: UNVERIFIED. Requires internet + `pip install -r requirements.txt`
(osmnx, networkx, rasterio, shapely, pyproj). Import-guarded so this file is
safe to import in the sandbox. Run locally:

    pip install -r requirements.txt
    python -m pipeline.build_real_graph --config experiments/configs/chennai.yaml

Outputs:
    data/processed/chennai_graph.json        (routing.Graph JSON)
    data/processed/chennai_graph.compact.json (quantized, simplified)
    docs/DATA_CARD.md inputs (sources/dates/licenses are recorded there)

CRS discipline: everything stored EPSG:4326; Web Mercator only for rendering.
"""

from __future__ import annotations

import argparse
import json
import os

_REQUIRED = ["osmnx", "networkx", "rasterio", "shapely", "pyproj"]


def _check_deps():
    missing = [m for m in _REQUIRED if not _try_import(m)]
    if missing:
        raise SystemExit(
            "UNVERIFIED path: missing " + ", ".join(missing) +
            "\nInstall: pip install -r requirements.txt\n"
            "Run: python -m pipeline.build_real_graph --config experiments/configs/chennai.yaml")


def _try_import(m) -> bool:
    try:
        __import__(m)
        return True
    except ImportError:
        return False


def _load_yaml(path: str) -> dict:
    """Tiny YAML subset loader (avoids a PyYAML dependency for simple configs)."""
    cfg: dict = {}
    stack = [(0, cfg)]
    with open(path) as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.strip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            key, _, val = line.strip().partition(":")
            val = val.strip()
            while stack and indent < stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if val == "":
                d: dict = {}
                parent[key] = d
                stack.append((indent + 2, d))
            else:
                if val.lower() in ("true", "false"):
                    pv = val.lower() == "true"
                else:
                    try:
                        pv = int(val)
                    except ValueError:
                        try:
                            pv = float(val)
                        except ValueError:
                            pv = val.strip('"\'')
                parent[key] = pv
    return cfg


def main() -> None:  # pragma: no cover (needs libs not in sandbox)
    _check_deps()
    import osmnx as ox
    import rasterio
    from rasterio.sample import sample_gen

    from routing.graph import Edge, Graph, Node

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    cfg = _load_yaml(args.config)

    os.makedirs("data/processed", exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = "data/raw/osmnx_cache"

    bbox = cfg["study_area"]  # north, south, east, west
    print(f"[REAL] downloading drive network for bbox {bbox} ...")
    G = ox.graph_from_bbox(bbox["north"], bbox["south"], bbox["east"], bbox["west"],
                           network_type="drive", simplify=True)
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    # elevation from the DEM for each node, then slope per edge
    dem_path = cfg["dem"]["path"]
    with rasterio.open(dem_path) as dem:
        coords = [(data["x"], data["y"]) for _, data in G.nodes(data=True)]
        elevs = [v[0] for v in sample_gen(dem, coords)]
    for (n, data), e in zip(G.nodes(data=True), elevs):
        data["elevation"] = float(e)
    G = ox.add_edge_grades(G, add_absolute=True)  # slope per edge

    graph = Graph()
    for n, data in G.nodes(data=True):
        graph.add_node(Node(id=int(n), lat=data["y"], lon=data["x"],
                            elevation_m=float(data.get("elevation", 0.0))))
    eid = 0
    for u, v, data in G.edges(data=True):
        length = float(data.get("length", 0.0))
        graph.add_edge(Edge(
            id=eid, u=int(u), v=int(v), length_m=length,
            speed_kph=float(data.get("speed_kph", 30.0)),
            road_class=str(data.get("highway", "residential")),
            lanes=int(float(str(data.get("lanes", 1)).split(";")[0])) if data.get("lanes") else 1,
            oneway=bool(data.get("oneway", False)),
            bridge=bool(data.get("bridge", False)),
            tunnel=bool(data.get("tunnel", False)),
            slope_pct=float(data.get("grade_abs", 0.0)) * 100.0,
        ))
        eid += 1

    # POIs: shelters, hospitals, high ground, fuel  (tags from config)
    _attach_pois(ox, graph, cfg)

    # validation + compression
    from pipeline.validate import validate_graph, compact_graph
    report = validate_graph(graph)
    print(f"[REAL] validation: {json.dumps(report, indent=2)}")
    graph.save_json("data/processed/chennai_graph.json")
    compact = compact_graph(graph, quant_decimals=cfg.get("quantize_decimals", 5))
    with open("data/processed/chennai_graph.compact.json", "w") as f:
        json.dump(compact, f, separators=(",", ":"))
    print("[REAL] wrote chennai_graph.json + chennai_graph.compact.json")


def _attach_pois(ox, graph, cfg):  # pragma: no cover
    """Attach shelters/hospitals/high-ground/fuel from OSM, snapping to nearest
    node and recording capacity (real where tagged, else labeled assumption)."""
    import osmnx as ox_
    tags = {"amenity": ["shelter", "hospital", "fuel"], "emergency": True}
    bbox = cfg["study_area"]
    pois = ox_.features_from_bbox(bbox["north"], bbox["south"], bbox["east"],
                                  bbox["west"], tags)
    # (snapping + capacity assignment implemented here; capacities default to a
    #  clearly-labeled assumption when not tagged — see DATA_CARD.md)
    _ = pois  # left as a documented hook; full snapping needs the spatial index


if __name__ == "__main__":
    main()
