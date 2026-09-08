# backend

The core engine — a **modular monolith** (per `ENG-ARCH-003`). Each module owns its
own tables and exposes writes only through its module API; cross-module direct writes
are prohibited (this is the future service-extraction seam).

Planned modules (see `docs/`):

- `identity` — accounts, principals, sessions, authz (SEC-001)
- `reference` — instruments, issuers, venues, currencies, calendars (DATA-001)
- `market` — source observations, accepted facts, reconciliation (DATA-002)
- `evidence` — evidence bundles, documents, provenance (EVID-001)
- `calculation` — deterministic calculators (isolated worker) (FIN-001)
- `monitoring` — rules, evaluation, alerts, coverage (MON-001)
- `rights` — data-rights & entitlement decisions (RIGHTS-001)
- `policy` — jurisdiction/capability policy engine (POL-001)
- `ai-gateway` — the single controlled path to model providers (AI-001)
- `api` — the public REST/JSON contract (API-001)

> Stack (Python / Node / other) to be decided.
