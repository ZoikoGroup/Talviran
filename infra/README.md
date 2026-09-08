# infra

Infrastructure & local development.

- **Local dev:** container setup for PostgreSQL 16+ and Redis (ephemeral cache).
- **IaC:** version-controlled infrastructure with reusable security/observability
  baseline modules and encrypted remote state (per `OPS-001`).
- **CI/CD:** build → tests → static/security/supply-chain gates → domain suites →
  staging → canary → rollout (per `OPS-001` / `QE-001`).

Launch substrate (per `ENG-ARCH-003 v4.1`): modular monolith in one Regional Cell +
a pre-approved DR cell; PostgreSQL system of record; object storage for artefacts;
durable jobs + transactional outbox (Kafka/Temporal deferred).

> Concrete tooling to be decided alongside the stack.
