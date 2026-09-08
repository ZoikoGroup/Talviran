# Talvrin

**A Zoiko Group platform — global, source-linked evidence and monitoring for public markets.**

> Reach a defensible view faster. Know when it changes.

Talvrin is a global public-markets research & monitoring platform. It gives users
**source-linked facts**, **reproducible financial calculations**, and **objective
monitoring/alerts** — without ever producing a platform-authored investment
recommendation (no buy/sell/hold, price targets, rankings or suitability advice).

The initial launch wedge is **UK gilts + US Treasuries**, but the core is
**global-by-design**: new jurisdictions, markets, vendors, currencies, languages and
asset classes are added through versioned **packs/adapters** — never by forking the core.

## Engineering doctrine

> Facts before language. Calculations before interpretation. Evidence before
> assertion. Policy before execution. Monitoring before engagement gimmicks.

- **Three separate truth classes:** `SourceObservation` → `AcceptedFact` → `CalculationResult`, tied together by an immutable `EvidenceBundle`. AI can never write canonical truth.
- **Bitemporal facts:** every fact carries valid-time and knowledge-time.
- **Fail-closed** rights and jurisdiction/policy checks, enforced server-side.
- **Monitoring is the recurring-value engine** — with proven coverage (a silently-dead rule is a product failure).
- **AI only explains** pre-computed evidence, through a single controlled gateway, and is removable without breaking facts, calculations or monitoring.

## Documentation

The controlled engineering estate lives in [`docs/`](docs/). Start with:

| Doc | Purpose |
|-----|---------|
| `DOC-001` | Documentation estate / governance index |
| `PRD-001` | Product requirements & functional spec |
| `ENG-ARCH-003 v4.1` | Backend architecture (the technical master) |
| `DATA-001 / DATA-002` | Canonical data model / ingestion & reconciliation |
| `RIGHTS-001` | Data rights & entitlements |
| `FIN-001` | Financial calculation methodology |
| `MON-001` | Monitoring rules & alerting |
| `EVID-001` | Evidence, provenance & document intelligence |
| `AI-001` | AI gateway, retrieval & model safety |
| `API-001` | Application & integration API contract |
| `POL-001` | Jurisdiction & regulatory policy |
| `SEC-001` | Security, privacy & access control |
| `QE-001` | Quality engineering & release standard |
| `OPS-001` | Platform operations, deployment & readiness |

## Status

Documentation baseline. Implementation not yet started.

---
_Confidential — Internal._
