# ResQFlow-X Backend (Phase 5)

FastAPI + SQLite + JWT. Offline sync, hazard-report reliability scoring,
admin/coordinator view, rate limiting, audit log.

## Verified in sandbox (pure stdlib)
- `reliability.py` — crowd-report reliability scorer (agreement, proximity,
  model-consistency, reporter history, recency). **Tested** (7 tests) and
  **evaluated against adversarial reporters** in `sim/report_eval.py`:
  precision stays ≥0.9 even at 60% adversarial reporters (never fooled into a
  false closure) — the key safety property. Recall is limited by reporter
  density (honest, documented).

## UNVERIFIED (needs pip; run locally)
```bash
pip install -r requirements.txt
uvicorn backend.app:app --reload      # OpenAPI docs at /docs
# or:
docker compose up
```
Endpoints: `POST /sos` (idempotent on client UUID), `POST /reports` (returns
reliability score), `GET /verified-closures`, `POST /admin/shelter`,
`POST /admin/closure`, `GET /admin/stats` (JWT admin), `GET /healthz`.

## Offline sync model
Client queues SOS/reports in IndexedDB (`pwa/src/sync.js`) with client-generated
UUIDs; server upserts idempotently (`INSERT OR IGNORE`). Conflict policy:
last-writer-wins by timestamp (documented). Flaky-network behavior is exercised
by the Playwright offline e2e test.

## Security / privacy
JWT role-based auth, rate limiting, input validation (Pydantic), audit log, no
secrets in repo (`RESQFLOW_SECRET` env). See `docs/PRIVACY.md`.
