# db

Database schema & migrations for the canonical model (`DATA-001`).

Principles (per `DATA-001` / `ENG-ARCH-003`):

- **One global PostgreSQL 16+ schema** — no country-specific tables or forks.
- Opaque UUIDv7 primary keys; external identifiers are aliases with rights lineage.
- **Bitemporal** truth: `valid_range` + `knowledge_range` with GiST exclusion
  constraints on `accepted_fact`.
- **Row-Level Security** scoped by `account_id` / `principal_id`.
- Least-privilege DB roles (e.g. the connector role cannot write `accepted_fact`;
  the AI role is read-only).
- **Expand-contract** (N-1 compatible) migrations only.

Ownership schemas: `identity`, `reference`, `market`, `evidence`, `calculation`,
`monitoring`, `governance`, `commercial`, `audit`.

> Migration tooling to be decided alongside the stack.
