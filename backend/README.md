# backend

Talvrin's core engine — a **modular monolith** (per `ENG-ARCH-003`). Each module
owns its own schema/tables and exposes writes only through its own service
layer; cross-module direct writes are prohibited (this is the future
service-extraction seam).

Stack: **FastAPI + SQLAlchemy 2.x (async) + Alembic + Postgres 16 + Redis**,
Python 3.12+, dependency/build managed with `uv`.

## Modules (`app/modules/`)

- `identity` — accounts, principals, sessions, auth (SEC-001)
- `reference` — instruments, issuers (DATA-001)
- `market` — connectors, source observations, reconciliation, accepted facts (DATA-002)
- `evidence` — evidence bundles/members, research-answer assembly (EVID-001)
- `calculation` — versioned calculation specs, golden-tested implementations, results (FIN-001)
- `monitoring` — rules, evaluation, alerts, delivery, coverage, dead-man watcher (MON-001)
- `research` — conversations/projects/messages/shares (encrypted at rest)
- `rights` — data-rights action decisions (RIGHTS-001)
- `policy` — the fail-closed Policy Decision Point + `AllowedOutputType` gate (POL-001)
- `audit` — cross-cutting event log
- `api` — the versioned REST contract (`/api/v1/...`, API-001)

Every user-facing response (`/research`, alerts, etc.) is gated through
`policy.pdp.evaluate()` against a closed `AllowedOutputType` enum before it can
reach a caller — this is structural, not a filter bolted on after the fact.
Talvrin never produces buy/sell/hold recommendations by design.

## Local setup

1. Bring up Postgres + Redis:
   ```
   docker compose -f ../infra/docker-compose.yml up -d
   ```
2. Copy `.env.example` to `.env` and adjust if your ports differ.
3. Install deps and migrate:
   ```
   uv sync
   uv run alembic upgrade head
   ```
4. Seed dev governance/reference data:
   ```
   uv run python scripts/seed_dev.py
   ```
5. Run the API:
   ```
   uv run uvicorn app.main:app --port 8000 --reload
   ```
   `GET /healthz` should return `{"status": "ok"}`.

**Only run one `uvicorn --reload` instance at a time.** Two processes racing
for the same port on Windows silently leaves one of them serving stale/broken
routes while the other holds the socket — requests can 404 unpredictably with
no error in either terminal.

## Testing

```
uv run pytest tests/unit          # no external services required
uv run pytest tests/integration   # requires Postgres + Redis running, migrated to head
uv run pytest tests/golden        # calculation golden-corpus / dual-implementation gate
```

**Integration tests use the same database your dev server points at**
(`DATABASE_URL` in `.env` — there is no separate test database yet). Their
`conftest.py` truncates every table it touches *before and after every test*.
Do not run `pytest tests/integration` while you're also testing the app
through the browser/frontend in the same session — it will silently wipe your
signed-in account, conversations, and any other live state mid-test. Giving
integration tests their own database is a known follow-up, not yet done.

Other scripts under `scripts/`:
- `ingest_dev_data.py` — runs the real market connectors against live sources
- `run_calculation_worker.py` / `run_monitoring_worker.py` — the async workers
  a production deployment runs out-of-process
- `run_deadman_watcher.py` — a genuinely separate process that pages if the
  monitoring worker's heartbeat goes stale (MON-001 §12.3)
- `approve_calculation_spec.py` / `rerun_calculation_spec_version.py` /
  `propose_golden_corpus_version.py` — calculation governance tooling
- `export_openapi.py` — regenerates the committed `openapi.json` snapshot

## Known infra flakiness

Docker Desktop on this dev machine occasionally restarts its VM, which stops
*every* container (Postgres and Redis included) with no error surfaced in the
app itself — symptoms are `ConnectionError: unexpected connection_lost()` or
`role "root" does not exist` in the Postgres logs. Check with `docker ps -a`
and `docker start infra-postgres-1 infra-redis-1` if the API starts throwing
connection errors; `alembic current` afterwards confirms no data loss.
