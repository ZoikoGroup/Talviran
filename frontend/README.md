# frontend

The web client. It consumes the backend REST/JSON API (`API-001`) — it holds **no**
business logic, never talks to data vendors or model providers directly, and treats
server-side policy/rights decisions as authoritative.

Planned surfaces (see `PRD-001` golden journeys):

- Search & instrument discovery
- Instrument evidence workspace (source-linked facts + freshness state)
- Deterministic calculators
- User-directed comparison
- Watchlists / saved research
- Monitoring rule creation + alert history
- AI-assisted research (evidence-constrained)
- Account / settings

> Stack (framework) to be decided.
