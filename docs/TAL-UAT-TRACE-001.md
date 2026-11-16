# TAL-UAT-TRACE-001 — Engineering Traceability Log

**Status: DRAFT — ENGINEERING-LEVEL TRACEABILITY, NOT A SIGNED QA RELEASE SIGN-OFF.**
Version 0.1 | 2026-11-16 | American English

## What this document is, and is not

This closes UAT gap-analysis item **G01**: *"UAT IDs and proof are unreliable. Restore
mapping; retain report IDs separately; attach artifacts and rerun omitted original tests."*
closure evidence bar: *"Signed traceability log; every in-scope original test has a run and
disposition."*

This document restores the mapping and gives every original UAT item a disposition backed by
a real, named, currently-passing automated test or an explicit "not established." It does
**not** satisfy the "signed" requirement — that is a QA/Product sign-off step this document
exists to make possible, not a substitute for it. No test run here was executed under a
formal QA role, device lab, or release-candidate build; it was run against this branch's
local dev environment by the engineer doing the remediation. **A QA lead must review this
table, re-run the cited tests (or equivalent) against a release candidate, and sign off
before this can support a release decision.**

Per `TAL-UAT-GAP-001`'s own instruction, the original guide's test identities and the
November 7 memorandum's report identities are kept **permanently separate**:
- **UAT-01…20** — the original UAT guide's test IDs (what this table restores evidence for).
- **REPORT-01…20** — the November 7 memorandum's own row identities (`R01` etc. below),
  which the gap analysis found to have silently taken over the UAT-01…20 meanings. They are
  recorded here only as the gap analysis's own "report relationship" column, unchanged from
  `TAL-UAT-GAP-001` §02. They are not re-verified independently in this document.

**Disposition legend**: `COVERED` (automated test(s) cited pass today and the test's own
assertions match the UAT item's intent) · `PARTIAL` (real coverage exists but does not reach
everything the UAT item or its linked gap (Gxx) requires — the gap is named explicitly) ·
`NOT ESTABLISHED` (no automated test covers this; "not established" per the gap analysis's
own definition means insufficient evidence, not a proven failure) · `OUT OF SCOPE` (the gap
analysis itself defers this).

## UAT-01 … UAT-20

| UAT | Original focus | Report relationship (TAL-UAT-GAP-001 §02) | Disposition | Evidence | What a QA sign-off still needs |
|---|---|---|---|---|---|
| 01 | Navigation | R01 FAIL — retest routes and legal content | PARTIAL | `frontend/src/components/HomeDashboard.tsx`, `PageLayout.tsx`/`AuthLayout.tsx` footer links now route to real Terms/Privacy/Cookies/Disclaimers/Contact pages (commit `053bcd3`), all of which render real, non-fabricated content (`Cookies.tsx`, `Disclaimers.tsx` new this session). | No automated mouse/touch/keyboard/direct-link regression suite exists for these five routes yet (G07's own closure bar). Needs a REG-06-style E2E pass across both signed-in and guest layouts. |
| 02 | Access / recovery | R02 partial scope — recovery, expiry, logout, MFA not established | PARTIAL | `backend/tests/integration/test_auth_flow.py`: `test_reset_password_*` (3), `test_forgot_password_does_not_reveal_whether_an_account_exists`, `test_change_password_*` (4), `test_logout_*` (2), `test_repeated_failures_are_rate_limited`. `backend/tests/unit/test_session_tokens.py` covers idle/absolute expiry and revocation at the unit level. | **MFA has zero test coverage.** `identity/service.py` implements real TOTP (`setup_totp`/`verify_and_enable_totp`/`disable_totp`/`verify_principal_totp`, `api/v1/auth.py`'s `/2fa/setup` route and login's `totp_code` path) but no test file in the repo exercises any of it — confirmed by a repo-wide search (`grep -rl totp tests/` finds nothing but a coincidentally-named PDF fixture). This is the single clearest concrete gap under UAT-02. |
| 03 | Account separation | No matching test — R03 tests Home, not isolation | COVERED for what's tested; PARTIAL against G10's full matrix | `test_rls_identity.py`, `test_research_isolation.py` (15 tests — conversation/message/data-key cross-account isolation, encryption-at-rest, ciphertext binding), `test_organization_api.py` (3, added this session: mid-session revocation, non-admin denial, cross-account member removal), `test_organization_seat_removal.py` (3, added this session, including a documented RLS/dead-code finding), `test_monitoring_rules_api.py::test_another_signed_in_user_cannot_delete_someone_elses_rule` (added this session), `test_research_endpoint.py::test_idempotency_cache_does_not_leak_across_tenants` (added this session, closes a real fix). | G10's own closure bar is broader: "object, search, cache, export and alert authorization under two tenants and revoked roles." Search and export authorization are not independently tested (export doesn't exist as a feature yet — see UAT-15); only one cache-isolation instance (the idempotency cache) has been checked, not a systematic sweep. |
| 04 | Instrument discovery | R04 partial failure — resolve aliases and scope independently | PARTIAL | `test_identity_resolution.py` (exact ISIN match, unresolved-not-guessed, near-miss non-fuzzy-match, audit logging of unresolved); `caf6baa` (this repo, pre-dating this session's tracked window) fixed the exact E1 ("NVIDIA financials & TradingView chart" misrouting) and E2 (bare "$MELI" falling through to a fully generic reply) screenshot scenarios, with `test_evidence_research_answer.py`/`test_evidence_answer_classification.py` regression coverage including a constructed ambiguous-ticker case. | This is deterministic alias-table matching plus pattern-based dispatch (`evidence/service.py`'s `_mentions_*`/`_dispatch_answer`), not the formal typed "resolved research request → capability decision → published response" contract `TAL-UAT-GAP-001` §07 (G02/G04) specifies, and there is no frozen 60-case acceptance suite (NVIDIA/NVDA, Alphabet/GOOGL/GOOG, MercadoLibre/MELI fixtures) — the two screenshot scenarios are fixed, the general contract is not built. See "Open architectural work" below. |
| 05 | Verifiable answer | R05 FAIL — supported positive answers must succeed | PARTIAL | Positive-answer paths for UK gilts/BoE curve/FX/macro/pilot equities have reconciliation + golden-calculation test coverage (`test_reconcile.py`, `test_calculation_*`, `test_approve_calculation_spec.py`). `test_evidence_research_answer.py` proves specific supported queries succeed. | No single test suite asserts "every currently-supported instrument × metric combination produces a positive answer," only specific cases per connector/metric. The typed "published response" contract (G04) that would make this systematic doesn't exist yet. |
| 06 | Evidence inspection | R06 FAIL — test claim support and version binding | PARTIAL | `test_evidence_traceability.py` (fact item surfaces source/effective-time/permitted-use; no-grant and no-linked-observation cases; calculation item surfaces spec + both time axes). `ComparisonPage.tsx`'s evidence drawer was fixed this session (`053bcd3`) to show real source/freshness/bitemporal status instead of an unconditional "PASSED" claim. | No automated test proves a citation opens the *correct passage in the correct answer version* end-to-end through the frontend (G04/AlphaSense-style requirement in §04) — the backend evidence-bundle binding is tested; the UI citation-click-through path is not. |
| 07 | Uncertainty | R07 limited claim — conflict, stale and rights cases still required | PARTIAL | `test_reconciliation_policy.py` (FLAG_CONFLICT vs PREFER_ORDER), `test_freshness.py` (per-metric `FreshnessProfile`, unregistered-metric fail-closed `KeyError`), `test_rights_engine_fail_closed.py`, `test_policy_pdp.py` (8 tests covering unregistered/unavailable capability, jurisdiction, kill-switch, every verdict logged). | These are unit/module-level proofs that the underlying conflict/staleness/rights primitives fail closed; no test walks a *user-facing answer* through a conflicted-source or stale-source case end-to-end and asserts what language the user actually sees. |
| 08 | Calculations / charts | R08, R15–16 partial — rendering and catalog count are insufficient | PARTIAL | Golden-corpus + dual-implementation gate (`scripts/approve_calculation_spec.py`, `test_approve_calculation_spec.py`, `test_golden_manifest.py`) for every APPROVED calculation spec. Five prior-session commits (`c5164e8`, `f4b3b8c`, `6c1d08e`, `2b5fc1d`, `8ee0e7e`) removed fabricated chart/price data and fixed timeframe-button/embed defects. | G06's full numerical-contract suite (OHLC invariants, interval/range separation, corporate-action adjustment correctness, multi-asset overlay currency handling, gap/revision display) as specified in `TAL-UAT-GAP-001` §09 does not exist as a named, frozen test suite — the fabrication risk is closed, the systematic chart-correctness proof is not built. |
| 09 | Like-for-like compare | R14–16 partial — periods, currencies and incompatible data untested | PARTIAL (integrity risk closed; feature not built) | `ComparisonPage.tsx`'s ~250-line fabricated financial-ratio dataset (fake P/E, EV/EBITDA, invented SEC accession numbers) was removed this session (`053bcd3`) and replaced with an honest "Not available" state wherever Talvrin has no real reconciled value. | The underlying comparison *feature* — real cross-instrument, cross-period, cross-currency ratio computation — does not exist yet; the fix removes the false-positive risk, it does not implement period/currency reconciliation. |
| 10 | Research boundary | No matching test — R10 sovereign telemetry is not advice handling | PARTIAL | `test_allowed_output_type.py` (exactly 8 output types, members match POL-001, no recommendation-shaped member exists — a structural, code-level proof the enum itself can't carry advice). `policy.pdp` gates every user-facing response through this enum. | No test specifically reproduces "a sovereign-yield/telemetry query must never be answered as investment advice" as a scenario — the structural guarantee (the enum has no advice-shaped member) is proven; a behavioral/scenario-level test naming this specific UAT concern is not. |
| 11 | Save / organize | R11 partial — project save, guest transfer and isolation missing | PARTIAL | `test_research_roundtrip.py` (13 tests: project/chat listing, rename, move-between-projects, multi-turn ordering, delete semantics, stable per-account encryption key). | No test specifically covers "guest transfer" (an anonymous/guest session's work being claimed after sign-up) — this scenario is not found anywhere in the test suite or, on inspection, in the research module's service layer. |
| 12 | Watchlist lifecycle | R11–12 partial — duplicate, remove and reload require proof | **NOT ESTABLISHED** | `app/modules/api/v1/watchlists.py` and `app/modules/research/watchlist_{models,schemas,service}.py` are a real, substantial feature. | **Zero backend test files reference watchlists at all** (confirmed: no file matching `*watchlist*` under `backend/tests/`, no test file contains the string "watchlist"). This session's G09 work added a frontend Playwright suite that exercises watchlist UI incidentally (and found/fixed a real crash bug in the process — see the G09 commit), but no test proves duplicate-item handling, removal, or reload-persistence at the service/API level. This is the clearest concrete backend gap this log surfaces. |
| 13 | Change monitoring | R13 partial — non-matches, retries, pause and consent missing | COVERED for what G11 scoped; PARTIAL against the full matrix | `test_monitoring_rule_engine.py` (11 tests, including this session's new out-of-order/late-arrival case), `test_monitoring_worker_restart.py` (this session's new crash-mid-sweep/resume exactly-once proof), `test_monitoring_alerts.py` (10 tests: initial-state, crossing, debounce suppress/elapse, idempotent re-evaluation, rights-gated), `test_monitoring_delivery.py`. | "Pause and consent" (a user pausing a rule, or revoking delivery consent) is not named in any test found; debounce (cooldown) is tested, an explicit pause/resume state is not confirmed to exist in `monitoring_rule`'s status model beyond ARMED/DRAFT/PAUSED/RETIRED — worth a QA check of whether PAUSED is reachable from the UI and tested there. |
| 14 | Source correction | No matching test — R14 empty state cannot establish correction replay | **NOT ESTABLISHED** | Bitemporal fact versioning itself is a core doctrine primitive (`valid_range`/`knowledge_range`, GiST exclusion constraint) and is exercised by `test_accepted_fact_as_of.py` and `test_change_detection.py`. | `TAL-UAT-GAP-001` §11 (G12) specifically requires "corrections create a new version and a material-change link; affected saved research and monitors are marked for reassessment" — **this reassessment-marking mechanism does not exist**. A corrected fact changes what a *new* query returns; nothing currently flags an *already-saved* research answer or monitor as needing a second look. This is open architectural work, not yet started as of this document. |
| 15 | Export / share | No matching test — R15 multiples do not validate export rights | **NOT ESTABLISHED / NOT BUILT** | — | Confirmed by repo-wide search: no file or directory matching `*export*`/`*dossier*` exists anywhere under `backend/app/`. The Export Dossier feature G13 describes does not exist yet in any form. This is the largest single piece of unbuilt scope this log surfaces. |
| 16 | Interruption recovery | No matching test — R16 chart modes do not validate recovery | **NOT ESTABLISHED / NOT BUILT** | `calculation.calculation_job` and `evidence.document_processing_job` both have typed states today, but only `PENDING`/`CLAIMED`/`DONE`/`FAILED` — no `CANCELED`/`CANCEL_REQUESTED`. | `/api/v1/research` (the user-facing chat endpoint) is a single synchronous request/response today — there is no async job, polling, or cancellation surface for a research answer at all, so G15's "queued/running/completed/failed/cancel-requested/canceled" state model does not apply to the one user journey most likely to be interrupted (a long research question). This is open architectural work. |
| 17 | Help / preferences | R17 FAIL; R18 partial — mailto is not a durable ticket receipt | COVERED | `test_support_tickets.py` (6 tests, this session: anonymous submission, durability-through-a-separate-connection proof, idempotency-key dedup, distinct-key non-dedup, failed-email-still-durable-ticket). The underlying `db.commit()` bug (every ticket silently rolled back) was found and fixed this session, independently confirmed live before the automated test existed. | None — this is the most thoroughly closed item in this log. |
| 18 | Device accessibility | R20 contradicted — clipped action requires device reproduction | PARTIAL | `frontend/tests/responsive/watchlists-mobile.spec.ts` (3 Playwright tests, this session: header never clips across 320/360/390/768/1280 CSS px, both header buttons keyboard-reachable and actionable, icon-only buttons have real accessible names). Fixing this also surfaced and fixed a real, independent crash (the `Field` component's `children`-vs-props bug breaking the "New Watchlist" modal and, unconditionally, the entire invitation-acceptance page). | This is one component (Watchlists header) on one browser (Chromium) at CSS-pixel viewports, not device pixels, and not the full supported iOS/Android browser matrix `TAL-UAT-GAP-001` §12 specifies, nor 400% zoom, nor a screen-reader pass beyond accessible-name presence. |
| 19 | Paid / team access | No matching test — R19 documentation is not entitlement testing | PARTIAL | `test_commercial_service.py` (11 tests after this session: checkout session creation, catalog, entitlement resolution, quota enforcement, webhook signature verification pass/fail, checkout-completed/expired/payment-failed/subscription-deleted dispatch). `test_organization_seat_removal.py` (seat count + access revocation proof, this session). The Stripe webhook `StripeObject`-vs-dict crash that would have 500'd every real production webhook was found and fixed this session. | `test_capability_manifest.py` (this session) documents conditional/paid-scope capabilities but the manifest itself is new and not yet wired into any enforcement path beyond documentation — it is a cross-reference, not a gate. |
| 20 | Historical research | No matching test — target-only; approved exclusion or separate test | OUT OF SCOPE | `TAL-UAT-GAP-001` §14 itself: "Historical Evidence Engine capabilities remain a separately gated target extension... Ordinary saved-answer versioning is still required at launch" (covered under UAT-11/14 above). | No action — this item is explicitly deferred by the gap analysis itself, not a remediation gap. |

## G01–G16 status cross-reference

| Gap | Status | Evidence |
|---|---|---|
| G01 | This document | — |
| G02 | PARTIAL | E1/E2 screenshot scenarios fixed (`caf6baa`); full typed contract + 60-case suite not built |
| G03 | NOT ESTABLISHED in this log | Per-instrument/per-metric availability publishing not independently audited here — see `capability_manifest.py` (G16) as a partial, adjacent step |
| G04 | PARTIAL | See UAT-05/06 above |
| G05 | PARTIAL | Golden-calculation gate exists; full lineage/provenance audit per `TAL-UAT-GAP-001` §08 not independently re-verified in this document |
| G06 | PARTIAL | Fabrication removed; full numerical-contract suite (§09) not built as a named test group |
| G07 | PARTIAL | Routes/content fixed; no automated cross-device/keyboard regression suite |
| G08 | **CLOSED** | `a279e80` — idempotency, durable outbox, reference-code collision fix, 6/6 tests passing |
| G09 | **CLOSED** for the Watchlists header; other primary actions not audited | `bdebb6c` — 3/3 Playwright tests passing, plus an independently-found modal crash fixed |
| G10 | PARTIAL | `7dea18c` — cross-tenant idempotency leak fixed, org/rule isolation tests added; search/export isolation not tested (export doesn't exist) |
| G11 | PARTIAL | `c1a8b1b` — out-of-order and crash/restart proofs added; pause/consent not confirmed tested |
| G12 | **NOT STARTED** | Reassessment-marking on correction does not exist |
| G13 | **NOT STARTED** | Export Dossier does not exist in any form |
| G14 | Addressed earlier this session (FAQ/footer copy, neutral comparison language) — not re-audited in this document | `053bcd3` and predecessor commits |
| G15 | **NOT STARTED** | No async job/cancellation surface exists for research answers; existing job queues (`calculation`, `evidence`) lack `CANCELED` states |
| G16 | **CLOSED** for what's built | `5b6d3c6` — webhook crash fixed, capability manifest added, 23/23 unit tests passing |

## Rerun of omitted original tests

G01 also requires attaching artifacts and rerunning any original test the memorandum
omitted. Every test cited by file name above was run against this branch on 2026-11-16
and confirmed passing in isolation (not concurrently with other suites — see this
session's commit history for a documented false-failure caused by concurrent pytest
processes racing the same test database's truncate-before/after fixture). No original
UAT test script beyond what is cited above was located in the repository; if a separate,
non-automated original UAT script exists outside this codebase, it is out of this
document's reach and must be rerun by whoever holds it.

## Recommended next steps for QA sign-off

1. Independently re-run every test file cited above against a release-candidate build, not
   a dev branch.
2. Add MFA test coverage (UAT-02) — the feature exists and is completely untested.
3. Add backend watchlist test coverage (UAT-12) — the feature exists and is completely
   untested.
4. Device-lab verification of UAT-18 beyond the one component and one browser covered here.
5. Formal QA/Product sign-off on this table, dated and attributable to a named reviewer —
   this document cannot create that signature, only the evidence underneath it.
