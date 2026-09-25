# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Talvrin (Zoiko Group) — a global, source-linked research and monitoring platform for public markets. It answers questions with **source-linked facts, reproducible calculations, and evidence-backed AI prose** — it never produces buy/sell/hold recommendations, price targets, or suitability advice; that perimeter is enforced in code (`policy.pdp`), not just policy. Engineering doctrine, restated because it explains otherwise-surprising code shapes throughout the backend:

- Three separate truth classes, never merged: `SourceObservation` (raw, as received) → `AcceptedFact` (reconciled canonical truth) → `CalculationResult` (deterministic, versioned, golden-tested). An immutable `EvidenceBundle` ties the ones behind any answer together. **AI can never write to any of these — it only reads and explains.**
- Bitemporal facts: every `accepted_fact` row carries both `valid_range` (when the fact was true in the world) and `knowledge_range` (when the platform believed it) — a GiST exclusion constraint enforces no two versions overlap on both.
- Identity resolution is deterministic-only, never fuzzy (an ISIN/ticker either matches an existing alias exactly or the observation is skipped and logged — never auto-created, never guessed).
- Fail-closed policy/rights checks, enforced server-side, never trusted from the client.
- Monitoring is treated as a first-class product surface, not an afterthought — a rule that silently stops evaluating is considered a product failure (hence the coverage-tracking + dead-man-watcher machinery).

The controlled engineering spec estate lives in `docs/` as numbered docs (`DATA-001`, `DATA-002`, `EVID-001`, `AI-001`, `RIGHTS-001`, `POL-001`, `FIN-001`, `MON-001`, `SEC-001`, etc. — see root `README.md` for the full index). Code comments cite these by section (e.g. "DATA-002 §7") — when a comment references one, that doc is the actual source of truth for *why*, not just decoration.

Two independent contributors have been building this concurrently (module-owned schemas make that tractable) — expect to see two distinct-but-consistent code voices across modules, and expect that a module you haven't touched yet may already solve a problem you're about to reach for a new pattern to solve.

## Commands

### Backend (`backend/`, run from that directory)

```
uv sync                                    # install/sync deps
uv run alembic upgrade head                # migrate the dev DB
uv run python -m scripts.seed_dev          # seed governance/reference/pilot data (idempotent)
uv run python -m scripts.seed_ai_gateway   # seed the AI provider/model registry (idempotent)
uv run python -m scripts.ingest_dev_data   # run real connectors against live sources into accepted_fact
uv run uvicorn app.main:app --port 8000 --reload   # GET /healthz -> {"status": "ok"}

uv run pytest tests/unit -q                # no external services required
uv run pytest tests/integration -q         # needs Postgres+Redis up, both DBs migrated to head
uv run pytest tests/golden -q              # calculation golden-corpus / dual-implementation gate
uv run pytest tests/integration/test_foo.py::test_specific_case -q   # single test

uv run ruff check .                        # lint
uv run mypy app/ scripts/                  # typecheck
```

Local Postgres/Redis: `docker compose -f infra/docker-compose.yml up -d` (Postgres image is `pgvector/pgvector:pg16` — a plain `postgres:16` will fail the moment a migration hits `CREATE EXTENSION vector`). **Integration tests run against a genuinely separate `talvrin_test` database** (`TEST_DATABASE_URL`/`TEST_ADMIN_DATABASE_URL` in `.env`, created by `infra/init-db/02-test-database.sql` on first cluster init) — it needs its own `alembic upgrade head` too:
```
ADMIN_DATABASE_URL=postgresql+asyncpg://talvrin:talvrin@localhost:5433/talvrin_test uv run alembic upgrade head
```
Forgetting this is the single most common cause of a wall of integration-test errors that look schema-related but aren't a real regression.

Only run one `uvicorn --reload` instance at a time (two racing for the same port on Windows silently leaves one serving stale routes, 404ing unpredictably with no error in either terminal). Docker Desktop on Windows dev machines occasionally drops its VM, killing every container silently — `ConnectionError: unexpected connection_lost()` or `role "root" does not exist` in the Postgres logs means check `docker ps -a` and restart the containers, not investigate the app.

### Frontend (`frontend/`, run from that directory)

```
npm install
npm run dev         # http://localhost:5173
npm run build        # tsc --noEmit && vite build - the real CI gate
npm run typecheck    # tsc --noEmit alone
```

`VITE_USE_MOCK=true` in `.env` gives an offline dev fallback (canned replies from `src/data/mockReply.ts`) — never true in a production build regardless of the env var, since `import.meta.env.PROD` is compile-time baked. No test runner or lint config exists in the frontend yet; `npm run build`'s `tsc --noEmit` is the only automated correctness gate.

## Architecture

### Backend: modular monolith, one schema per module

Modules under `app/modules/`, each owning its own Postgres schema and writable only through its own service layer (cross-module direct writes are prohibited — this is the intended future service-extraction seam):

- `identity` — Supabase Auth (GoTrue) is the credential/session engine (see `identity/supabase_auth.py`); this app's own `identity.principal`/`account` tables mirror it locally, keyed on `supabase_user_id`, for RLS and everything else to join against.
- `reference` — instruments/issuers/aliases. `instrument_type` is a plain string (not an enum) discriminating which 1:1 "asset-adapter" table holds type-specific terms — today only `FiSovereignTerms` (bond terms) exists; equities/FX/macro deliberately don't get an adapter table since only price data is needed for them so far.
- `market` — connectors + the ingestion pipeline (`DATA-002`). See "The connector pipeline" below.
- `evidence` — evidence bundles/members (the FACT/CALCULATION/DOCUMENT_SPAN discriminated union behind every answer), plus the newer document-intelligence pipeline (acquire → parse → embed, `EVID-001`) backing semantic + lexical retrieval over documents (pgvector + Postgres FTS).
- `calculation` — versioned `calculation_specification`s that must pass a golden-corpus + dual-independent-implementation gate (`scripts/approve_calculation_spec.py`) before moving DRAFT → APPROVED; nothing computes under an unapproved spec. Job-queue handoff (`pipeline/job_queue.py`, `FOR UPDATE SKIP LOCKED`) rather than synchronous compute-in-request.
- `monitoring` — rules → evaluations → alerts → delivery, plus **two independent liveness concepts** that are easy to conflate: coverage tracking (is this specific rule being evaluated on schedule) vs. the dead-man watcher (is the evaluator process itself alive at all) — deliberately run as separate processes so one can't be trusted to report the other's death.
- `ai_gateway` — the **single controlled path** to any model provider (`AI-001`). See "The AI Gateway" below.
- `research` — conversations/projects/messages/shares, envelope-encrypted at rest per account.
- `rights` / `policy` — `rights.evaluate_action` gates data-usage actions (retrieve/store/embed/display are independently evaluated — a rights profile might permit indexing a document's text but not sending it to a third-party embedding API); `policy.pdp` is the fail-closed Policy Decision Point every user-facing response is gated through against a closed `AllowedOutputType` enum, which structurally excludes anything recommendation-shaped.
- `audit` — cross-cutting event log.
- `api/v1` — the versioned REST contract.

### The connector pipeline (`market/connectors/*`, `market/pipeline/*`)

Every data source (UK DMO gilts, Bank of England yield curve, Frankfurter FX, DBnomics macro, Twelve Data equities) follows the same shape, defined structurally by `connectors/base.py`'s `Connector` Protocol: `discover → acquire → verify_transport → identify_schema → parse → checkpoint → health`. A connector is *forbidden* from resolving identity, reconciling, or writing `accepted_fact` — it only acquires and normalises. Callers must go through `validate_and_parse()`, never call `.parse()` directly, or the transport/schema checks are dead code.

Downstream, `pipeline/ingest_tail.py`'s `ingest_and_reconcile()` is the shared tail every metric-specific `ingest_*_candidate` function calls: get-or-create a `SourceObservation` (idempotent on a semantic key hash), then `reconcile.py::reconcile_and_publish()` — **the only code path allowed to write `accepted_fact`**. Reconciliation groups candidates by exact value; a `ReconciliationPolicy` (per-metric, not global) decides `FLAG_CONFLICT` vs `PREFER_ORDER` when more than one source disagrees (today every metric has exactly one source, so this never fires in production, but the multi-source path is built and tested, not deferred).

Identity resolution (`pipeline/identity_resolution.py`) is deterministic-only: exact alias match (ISIN, or `TICKER` as `"{EXCHANGE}:{SYMBOL}"`) or the observation is skipped and logged — never fuzzy-matched, never auto-creates a new `reference.instrument`. Subjects with no natural "instrument" identity (an FX pair, a yield-curve tenor point, a macro series) skip `reference.instrument` entirely and use a fixed `uuid.uuid5()` derived from a descriptive string instead — see `curve_ingest.py`, `fx_ingest.py`, `macro_ingest.py` for the pattern.

Freshness (`market/freshness.py`) is computed per-call from a `FreshnessProfile` keyed by `metric_id`; an unregistered `metric_id` **raises `KeyError`** rather than silently defaulting to "current" — every new metric's `FreshnessProfile` must ship in the same change as the metric itself.

There is no scheduler of any kind — `scripts/ingest_dev_data.py` (gilt/curve, which also triggers the pricing job) plus `scripts/_connector_registry.py` (the three newer connectors) are manually-invoked dev scripts. A production recurring-ingestion job is real, unbuilt future work, not an oversight.

### The AI Gateway (`ai_gateway/`)

`gateway.invoke_model()` is the only sanctioned entry point — no other module may import `ai_gateway/providers/*` directly. Per call: kill-switch check → PDP evaluation (same gate every other capability uses) → render a grounded prompt from a caller-supplied `evidence_bundle_id` (refuses to generate anything if the bundle has no renderable items — no bare-string prompts are accepted, so an ungrounded call is structurally impossible) → resolve the PRODUCTION model for the task_type → call the provider → validate the response (citation indices must reference real evidence items, no recommendation-shaped language) → on validation failure, exactly one bounded regeneration attempt, then give up. Every attempt is written to `ai_model_execution` (forensic/audit row) regardless of outcome.

**Product invariant, stated in the module's own docstring: "AI is fully removable" — the platform must keep answering correctly with the Gateway turned off.** Concretely, `InvokeRejected` (no PRODUCTION model, PDP deny, validation failed twice, provider unreachable) must always be handled by falling back to the rule-based answer in `evidence/service.py`, never surfaced as a request failure. `research.py::_try_ai_composed_text` is where that fallback boundary lives today.

Currently in production: `talvrin-go` → Groq (`openai/gpt-oss-20b`), `talvrin-pro` → Gemini (`gemini-flash-lite-latest`) — both proven live before promotion to `PRODUCTION` status, the same governance discipline `approve_calculation_spec.py` applies to calc specs. `scripts/seed_ai_gateway.py` seeds this registry and documents *why* each model was chosen (including a dead-end: `llama-3.3-70b-versatile` doesn't exist on the configured Groq key at all, found via a real API call, not assumed from docs).

### Frontend: sourced live from the backend, not cached locally

`App.tsx` loads the signed-in account's chats/projects from the real API on mount (`listChats`/`listProjects`) — there is deliberately **no local cache of chat content** (a prior version cached everything in one shared `localStorage` key with no account-scoping, which leaked one account's conversations into another's browser session; do not reintroduce a local content cache without account-scoping it). A chat's full transcript is fetched lazily (`getChat`) only once it's actually opened, guarded against duplicate concurrent fetches via a `pendingChatLoads` ref. The app always opens on a fresh compose screen on load rather than resuming the last-open chat.

Rename/move/delete for chats and projects are optimistic-with-rollback: the local state updates immediately, and a failed backend call reverts it and surfaces a dismissible error banner (`syncError`) rather than silently drifting from the server.

Historical assistant messages loaded from the backend render as **plain text only** — the rich facts-table/citations rendering only exists for an answer received live in the current session, since `research.message.content` persists just the plain reply text, not the structured facts/citations that were computed at request time.

## Known sharp edges worth re-checking before assuming "it just works"

- A new external connector's actual response shape must be verified live (curl it) before writing a parser against assumed/documented shape — this codebase has caught real, wrong assumptions this way more than once (an API's "v1" being quietly deprecated in favour of "v2" with a different shape; a symbol format assumption that turned out wrong).
- Twelve Data's free tier does not cover every symbol (many return "available starting with the Grow/Venture plan") — a `RecordIssue`/quarantine on a specific symbol is not necessarily a bug.
- Windows + `core.autocrlf` can silently corrupt checksum-pinned fixture files (golden corpora) on checkout — `.gitattributes` pins the affected paths to `-text`; if a golden test fails only on a fresh Windows checkout, check bytes against the committed blob before assuming the math is wrong.
- Root/`backend`/`frontend`/`db` `README.md` files describe an earlier, much less complete state of the project (frontend's says "no backend connected yet"; root's says "implementation not yet started") — trust the code and this file over those for current state.
