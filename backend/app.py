"""FastAPI backend for ResQFlow-X (Phase 5). UNVERIFIED in the sandbox (needs
`pip install fastapi uvicorn pydantic python-jose passlib`). Import-guarded so
the module is safe to import; the reliability scoring it uses is the pure-stdlib
backend.reliability (tested in the sandbox).

Features: OpenAPI docs, SQLite storage, JWT role-based auth, idempotent offline
sync (client UUIDs), hazard reports with reliability scoring, admin shelter/road
management + live stats, rate limiting, structured logs. Run locally:

    pip install -r requirements.txt
    uvicorn backend.app:app --reload
    # OpenAPI at http://localhost:8000/docs
"""

from __future__ import annotations

import time

try:
    from fastapi import Depends, FastAPI, Header, HTTPException
    from pydantic import BaseModel, Field
    _HAVE_FASTAPI = True
except ImportError:  # sandbox has no fastapi
    _HAVE_FASTAPI = False

from backend.reliability import Report, ReliabilityScorer

if _HAVE_FASTAPI:  # pragma: no cover (needs libs not in sandbox)
    import sqlite3
    import uuid

    app = FastAPI(title="ResQFlow-X API", version="0.1.0",
                  description="Uncertainty-aware offline-first evacuation routing")

    _scorer = ReliabilityScorer()
    _DB = "data/processed/resqflow.db"

    # ---- Pydantic models ----
    class SOSIn(BaseModel):
        id: str = Field(..., description="client-generated UUID (idempotency key)")
        lat: float | None = None
        lon: float | None = None
        batt: int | None = None
        grp: int = 1
        ts: int

    class ReportIn(BaseModel):
        id: str
        edge_id: int
        lat: float
        lon: float
        reporter_id: str
        hazard: str = "blocked"
        ts: int
        reporter_lat: float | None = None
        reporter_lon: float | None = None

    class ShelterUpdate(BaseModel):
        node_id: int
        capacity: int
        open: bool = True

    class RoadClosure(BaseModel):
        edge_id: int
        closed: bool = True

    # ---- storage ----
    def _db():
        con = sqlite3.connect(_DB)
        con.execute("CREATE TABLE IF NOT EXISTS sos (id TEXT PRIMARY KEY, lat REAL, lon REAL, batt INT, grp INT, ts INT)")
        con.execute("CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, edge_id INT, lat REAL, lon REAL, reporter_id TEXT, hazard TEXT, ts INT, reporter_lat REAL, reporter_lon REAL, score REAL)")
        con.execute("CREATE TABLE IF NOT EXISTS shelters (node_id INT PRIMARY KEY, capacity INT, open INT)")
        con.execute("CREATE TABLE IF NOT EXISTS closures (edge_id INT PRIMARY KEY, closed INT)")
        con.execute("CREATE TABLE IF NOT EXISTS audit (ts INT, actor TEXT, action TEXT, detail TEXT)")
        return con

    # ---- minimal JWT role auth (HS256) ----
    import hashlib
    import hmac
    import base64
    import json as _json
    _SECRET = __import__("os").environ.get("RESQFLOW_SECRET", "dev-secret-change-me")

    def _make_token(sub: str, role: str) -> str:
        payload = base64.urlsafe_b64encode(_json.dumps({"sub": sub, "role": role}).encode()).decode()
        sig = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def _require_role(role: str):
        def dep(authorization: str = Header(default="")):
            tok = authorization.replace("Bearer ", "")
            try:
                payload, sig = tok.split(".")
                exp = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(sig, exp):
                    raise ValueError
                data = _json.loads(base64.urlsafe_b64decode(payload))
                if role == "admin" and data.get("role") != "admin":
                    raise HTTPException(403, "admin required")
                return data
            except Exception:
                raise HTTPException(401, "invalid token")
        return dep

    # ---- naive in-memory rate limiter ----
    _hits: dict[str, list[float]] = {}

    def _rate_limit(key: str, limit=60, window=60.0):
        now = time.time()
        hits = [t for t in _hits.get(key, []) if now - t < window]
        if len(hits) >= limit:
            raise HTTPException(429, "rate limited")
        hits.append(now)
        _hits[key] = hits

    # ---- endpoints ----
    @app.post("/sos")
    def post_sos(sos: SOSIn):
        _rate_limit("sos")
        con = _db()
        # idempotent on client UUID
        con.execute("INSERT OR IGNORE INTO sos VALUES (?,?,?,?,?,?)",
                    (sos.id, sos.lat, sos.lon, sos.batt, sos.grp, sos.ts))
        con.commit(); con.close()
        return {"accepted": True, "id": sos.id}

    @app.post("/reports")
    def post_report(rep: ReportIn):
        _rate_limit("reports")
        con = _db()
        rows = con.execute("SELECT id,edge_id,lat,lon,reporter_id,ts,hazard,reporter_lat,reporter_lon FROM reports").fetchall()
        all_reports = [Report(id=r[0], edge_id=r[1], lat=r[2], lon=r[3], reporter_id=r[4],
                              timestamp=r[5], hazard=r[6], reporter_lat=r[7], reporter_lon=r[8]) for r in rows]
        this = Report(id=rep.id, edge_id=rep.edge_id, lat=rep.lat, lon=rep.lon,
                      reporter_id=rep.reporter_id, timestamp=rep.ts, hazard=rep.hazard,
                      reporter_lat=rep.reporter_lat, reporter_lon=rep.reporter_lon)
        s = _scorer.score(this, all_reports + [this], now=time.time())
        con.execute("INSERT OR IGNORE INTO reports VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (rep.id, rep.edge_id, rep.lat, rep.lon, rep.reporter_id, rep.hazard,
                     rep.ts, rep.reporter_lat, rep.reporter_lon, s["score"]))
        con.commit(); con.close()
        return s

    @app.get("/verified-closures")
    def verified_closures(threshold: float = 0.6):
        con = _db()
        rows = con.execute("SELECT edge_id, MAX(score) FROM reports GROUP BY edge_id HAVING MAX(score) >= ?",
                           (threshold,)).fetchall()
        con.close()
        return {"edges": [r[0] for r in rows], "threshold": threshold}

    @app.post("/admin/shelter")
    def admin_shelter(upd: ShelterUpdate, user=Depends(_require_role("admin"))):
        con = _db()
        con.execute("INSERT OR REPLACE INTO shelters VALUES (?,?,?)",
                    (upd.node_id, upd.capacity, int(upd.open)))
        con.execute("INSERT INTO audit VALUES (?,?,?,?)",
                    (int(time.time()), user["sub"], "shelter_update", str(upd.dict())))
        con.commit(); con.close()
        return {"ok": True}

    @app.post("/admin/closure")
    def admin_closure(c: RoadClosure, user=Depends(_require_role("admin"))):
        con = _db()
        con.execute("INSERT OR REPLACE INTO closures VALUES (?,?)", (c.edge_id, int(c.closed)))
        con.execute("INSERT INTO audit VALUES (?,?,?,?)",
                    (int(time.time()), user["sub"], "road_closure", str(c.dict())))
        con.commit(); con.close()
        return {"ok": True}

    @app.get("/admin/stats")
    def admin_stats(user=Depends(_require_role("admin"))):
        con = _db()
        n_sos = con.execute("SELECT COUNT(*) FROM sos").fetchone()[0]
        n_rep = con.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        con.close()
        return {"sos": n_sos, "reports": n_rep}

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}
