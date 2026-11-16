"""The single, explicit statement of what Talvrin actually supports today
(UAT gap-analysis G16: "payments, preferences, privacy, IPO states and
target-only history need explicit scope and tests").

Before this module, "what does the platform support" lived only implicitly,
scattered across:
  - `frontend/src/data/globalAssets.ts`'s `VERIFIED_LIVE_SYMBOLS` set (which
    catalog entries are real vs illustrative)
  - `backend/scripts/seed_dev.py`'s `PILOT_EQUITIES` (which equities actually
    get ingested)
  - `app/modules/market/freshness.py`'s `FreshnessProfile` registry (which
    metric_ids are even real - an unregistered one raises `KeyError`, DATA-002
    §14.1)
  - `app/modules/monitoring/rule_engine.py`'s `SCALAR_VALUE_KEYS` /
    `CALCULATION_SCALAR_VALUE_KEYS` (which metrics a monitoring rule can
    actually target)
  - a string-matching cascade of `_mentions_*`/`_not_yet_connected_reply`
    guards in `app/modules/evidence/service.py` (which asset classes get an
    honest refusal instead of an attempted answer)

This module does NOT replace any of those - rewiring five independent
mechanisms that already work is its own, much riskier, change. What it does
is give those mechanisms a single document to be checked against: every
claim below is traceable to one of the registries/files named per entry, so
"is X supported" has one place to look, and a drift between this file and
any of those five can be caught by diffing against them (see
`tests/unit/test_capability_manifest.py`, which automates that diff for the
two cases where it's cheap to do so: the frontend's VERIFIED_LIVE_SYMBOLS
set, and evidence/service.py's literal `asset_class=` refusal strings).

Reason codes reuse `app.core.errors.ErrorCode` (API-001's existing,
approved vocabulary) rather than inventing a parallel one:
  - CAPABILITY_UNAVAILABLE: no connector/feature exists for this asset
    class at all (today's `_not_yet_connected_reply` guards, and the gap
    this manifest's `monitor=False` entries describe for metrics outside
    `SCALAR_VALUE_KEYS`/`CALCULATION_SCALAR_VALUE_KEYS`).
  - RIGHTS_RESTRICTED: a connector/feature exists but entitlement/rights
    gating can deny it for a given account (reserved for future use by this
    manifest; nothing below sets it today - see the module docstring's
    "does NOT replace" note above).

IPOs are deliberately included among the unsupported entries even though no
IPO feature exists anywhere in the codebase: the UAT gap report specifically
asked for IPO states to have "explicit scope", and evidence/service.py
already refuses IPO queries honestly (`_mentions_ipo` ->
`_not_yet_connected_reply(..., asset_class="IPOs")`) - this entry is what
makes that refusal a documented, intentional scope decision rather than a
silent omission someone has to rediscover by reading routing code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import ErrorCode

# ---------------------------------------------------------------------------
# Supported today
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityEntry:
    """One asset class's real, current capability surface.

    `metric_ids` are the literal `metric_id` strings this platform's own
    freshness/monitoring registries key on (empty for asset classes that
    aren't connected at all). `symbols` are the literal identity-resolution
    keys (ISIN, or `{EXCHANGE}:{SYMBOL}` ticker aliases, or a curve/FX
    descriptive string) a real query or monitoring rule would need to use -
    not display labels.

    The five booleans answer exactly the question UAT gap G16 asked:
    "what capabilities are actually available". `monitor=True` means a
    monitoring rule can target this metric_id *today*, per
    `monitoring/rule_engine.py`'s `SCALAR_VALUE_KEYS`/
    `CALCULATION_SCALAR_VALUE_KEYS` - not that every condition type is
    wired for it. `price` is read loosely for non-instrument subjects (a
    curve point, an FX rate, a macro indicator level) as "a current value
    is retrievable", not literally an instrument price.
    """

    asset_class: str
    metric_ids: tuple[str, ...]
    symbols: tuple[str, ...]
    price: bool
    chart: bool
    compare: bool
    monitor: bool
    export: bool
    reason: ErrorCode | None = None
    notes: str = ""
    source_refs: tuple[str, ...] = field(default_factory=tuple)


CAPABILITY_MANIFEST: tuple[CapabilityEntry, ...] = (
    CapabilityEntry(
        asset_class="UK gilts",
        metric_ids=(
            "GILT_REFERENCE_TERMS",
            "UK_GILT_NOMINAL_SPOT_CURVE",
            "MODEL_IMPLIED_CLEAN_PRICE",
            "GILT_MARKET_CLOSE_PRICE",
        ),
        symbols=(),  # identity is per-ISIN (reference.instrument) or a
        # curve-tenor uuid5, never a display ticker - see
        # market/pipeline/curve_ingest.py.
        price=True,
        chart=True,
        compare=True,
        monitor=True,  # UK_GILT_NOMINAL_SPOT_CURVE and
        # MODEL_IMPLIED_CLEAN_PRICE are both in rule_engine.py's registries.
        export=True,
        reason=None,
        notes=(
            "UK DMO gilt reference terms, BoE nominal spot curve, and the "
            "curve-derived model-implied clean price (calculation_result, "
            "never accepted_fact - see MODEL_IMPLIED_CLEAN_PRICE's own "
            "freshness profile docstring)."
        ),
        source_refs=(
            "app/modules/market/freshness.py (4 FreshnessProfile entries)",
            "app/modules/monitoring/rule_engine.py (both registries)",
        ),
    ),
    CapabilityEntry(
        asset_class="US treasuries",
        metric_ids=("TREASURY_SECURITY_REFERENCE_TERMS", "US_TREASURY_PAR_YIELD_CURVE"),
        symbols=(),
        price=True,
        chart=True,
        compare=True,
        monitor=False,  # neither metric_id is in SCALAR_VALUE_KEYS or
        # CALCULATION_SCALAR_VALUE_KEYS today - a monitoring rule targeting
        # a US Treasury metric is rejected by rule_engine.py's final
        # `unknown or unwatchable metric_id` branch.
        export=True,
        reason=None,
        notes=(
            "US Treasury par yield curve and reference terms are live "
            "(accepted_fact-backed), but no monitoring rule can target them "
            "yet - a real, narrow gap this entry documents rather than "
            "silently assumes parity with UK gilts."
        ),
        source_refs=(
            "app/modules/market/freshness.py",
            "app/modules/monitoring/rule_engine.py (absence, not presence)",
        ),
    ),
    CapabilityEntry(
        asset_class="GBP/USD",
        metric_ids=("FX_SPOT_RATE",),
        symbols=("GBP/USD",),
        price=True,
        chart=True,
        compare=True,
        monitor=False,  # same gap as US treasuries: FX_SPOT_RATE is not in
        # either rule_engine.py registry.
        export=True,
        reason=None,
        notes="Frankfurter (ECB reference rates), once per EU business day.",
        source_refs=("app/modules/market/freshness.py",),
    ),
    CapabilityEntry(
        asset_class="US equities (pilot list)",
        metric_ids=("EQUITY_EOD_PRICE",),
        # Real identity-resolution aliases (scripts/seed_dev.py's
        # PILOT_EQUITIES + equity_ingest.py's "{EXCHANGE}:{SYMBOL}" format),
        # NOT the frontend's display tickers - see this module's own
        # docstring and test_capability_manifest.py for the mismatch that
        # surfaces between the two.
        symbols=("NASDAQ:AAPL", "NASDAQ:MSFT", "NASDAQ:VOD", "NYSE:BP", "NASDAQ:AZN"),
        price=True,
        chart=True,
        compare=True,
        monitor=False,  # EQUITY_EOD_PRICE is not in either rule_engine.py
        # registry either - today only two of the ten real metric_ids in
        # the whole platform are monitorable, both UK-gilt-specific.
        export=True,
        reason=None,
        notes=(
            "Twelve Data end-of-day prices for exactly 5 pilot tickers "
            "(scripts/seed_dev.py PILOT_EQUITIES) - the free tier doesn't "
            "cover every symbol, so this list is deliberately small, not a "
            "sample of a larger supported set."
        ),
        source_refs=(
            "backend/scripts/seed_dev.py (PILOT_EQUITIES)",
            "app/modules/market/freshness.py",
        ),
    ),
    CapabilityEntry(
        asset_class="UK/US macroeconomic indicators",
        metric_ids=("MACRO_GDP", "MACRO_CPI"),
        symbols=(),
        price=True,
        chart=True,
        compare=False,  # not an instrument/ticker; not wired into the
        # symbol-keyed Compare dashboard - unverified in this pass beyond
        # that structural observation, flagged rather than guessed.
        monitor=False,
        export=True,
        reason=None,
        notes="DBnomics GDP and CPI series for UK and US.",
        source_refs=("app/modules/market/freshness.py",),
    ),
    # -----------------------------------------------------------------------
    # Not supported - every one of these is a real `_not_yet_connected_reply`
    # guard in evidence/service.py today (asset_class strings below are
    # copied verbatim from that module's `_mentions_*` dispatch, confirmed
    # in test_capability_manifest.py), not a hypothetical future gap.
    # -----------------------------------------------------------------------
    CapabilityEntry(
        asset_class="ETFs",
        metric_ids=(),
        symbols=(),
        price=False,
        chart=False,
        compare=False,
        monitor=False,
        export=False,
        reason=ErrorCode.CAPABILITY_UNAVAILABLE,
        notes="No connector exists; queries are honestly refused, never fabricated.",
        source_refs=("app/modules/evidence/service.py (_mentions_etf)",),
    ),
    CapabilityEntry(
        asset_class="cryptocurrencies",
        metric_ids=(),
        symbols=(),
        price=False,
        chart=False,
        compare=False,
        monitor=False,
        export=False,
        reason=ErrorCode.CAPABILITY_UNAVAILABLE,
        notes="No connector exists; queries are honestly refused, never fabricated.",
        source_refs=("app/modules/evidence/service.py (_mentions_crypto)",),
    ),
    CapabilityEntry(
        asset_class="commodities",
        metric_ids=(),
        symbols=(),
        price=False,
        chart=False,
        compare=False,
        monitor=False,
        export=False,
        reason=ErrorCode.CAPABILITY_UNAVAILABLE,
        notes="No connector exists; queries are honestly refused, never fabricated.",
        source_refs=("app/modules/evidence/service.py (_mentions_commodity)",),
    ),
    CapabilityEntry(
        asset_class="IPOs",
        metric_ids=(),
        symbols=(),
        price=False,
        chart=False,
        compare=False,
        monitor=False,
        export=False,
        reason=ErrorCode.CAPABILITY_UNAVAILABLE,
        notes=(
            "No IPO feature exists anywhere in the codebase (pre/post-IPO "
            "states, lockups, allocations). Honestly refused today - this "
            "entry is what makes that an explicit, documented scope "
            "decision (UAT gap G16) rather than a silent gap someone "
            "rediscovers later."
        ),
        source_refs=("app/modules/evidence/service.py (_mentions_ipo)",),
    ),
    CapabilityEntry(
        asset_class="mutual funds",
        metric_ids=(),
        symbols=(),
        price=False,
        chart=False,
        compare=False,
        monitor=False,
        export=False,
        reason=ErrorCode.CAPABILITY_UNAVAILABLE,
        notes="No connector exists; queries are honestly refused, never fabricated.",
        source_refs=("app/modules/evidence/service.py (_mentions_mutual_fund)",),
    ),
    CapabilityEntry(
        asset_class="global market indices",
        metric_ids=(),
        symbols=(),
        price=False,
        chart=False,
        compare=False,
        monitor=False,
        export=False,
        reason=ErrorCode.CAPABILITY_UNAVAILABLE,
        notes="No connector exists; queries are honestly refused, never fabricated.",
        source_refs=("app/modules/evidence/service.py (_mentions_global_index)",),
    ),
    CapabilityEntry(
        asset_class="equity fundamentals / deep research",
        metric_ids=(),
        symbols=(),
        price=False,
        chart=False,
        compare=False,
        monitor=False,
        export=False,
        reason=ErrorCode.CAPABILITY_UNAVAILABLE,
        notes=(
            "Deep equity research (ratios, fundamentals narrative) was "
            "removed 2026-10-21 after a real incident (see "
            "_not_yet_connected_reply's own docstring: a live query was "
            "answered with a fabricated Apple report). Only EOD price for "
            "the pilot list is live for equities - see that entry above."
        ),
        source_refs=("app/modules/evidence/service.py (_mentions_deep_equity)",),
    ),
)


def get_capability(asset_class: str) -> CapabilityEntry | None:
    """Case-sensitive, exact match - asset_class strings here are contract
    values (they're asserted against evidence/service.py's own literals),
    not free-text to fuzzy-match against."""
    for entry in CAPABILITY_MANIFEST:
        if entry.asset_class == asset_class:
            return entry
    return None


def supported_asset_classes() -> tuple[str, ...]:
    return tuple(e.asset_class for e in CAPABILITY_MANIFEST if e.reason is None)


def unsupported_asset_classes() -> tuple[str, ...]:
    return tuple(e.asset_class for e in CAPABILITY_MANIFEST if e.reason is not None)


def all_supported_symbols() -> tuple[str, ...]:
    """Every real identity-resolution symbol this manifest claims is live -
    used by test_capability_manifest.py to cross-check against
    frontend/src/data/globalAssets.ts's VERIFIED_LIVE_SYMBOLS set."""
    symbols: list[str] = []
    for entry in CAPABILITY_MANIFEST:
        if entry.reason is None:
            symbols.extend(entry.symbols)
    return tuple(symbols)
