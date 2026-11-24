"""Tests for app/core/capability_manifest.py (UAT gap G16).

Two kinds of check here:
  1. Internal consistency - the manifest's own shape makes sense (no
     duplicate asset classes, unsupported entries don't quietly claim a
     capability, every reason code is a real ErrorCode member, etc.)
  2. Cross-checks against the scattered mechanisms the manifest is meant to
     describe, so a future edit to either side that silently drifts gets
     caught here rather than discovered in production. Two such mechanisms
     are checked automatically by reading the real source files (not
     hardcoded copies): evidence/service.py's `_not_yet_connected_reply`
     guards, and frontend/src/data/globalAssets.ts's VERIFIED_LIVE_SYMBOLS
     set.

The frontend cross-check surfaces a real, pre-existing mismatch between the
two layers' equity ticker conventions (backend NASDAQ/NYSE ADR aliases vs
frontend LSE-style tickers, and Vodafone missing from the frontend list
entirely) - see test_equity_symbols_partially_cross_reference_frontend
below, which asserts the known-good overlap AND names the known gaps
explicitly rather than silently ignoring them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.capability_manifest import (
    CAPABILITY_MANIFEST,
    all_supported_symbols,
    get_capability,
    supported_asset_classes,
    unsupported_asset_classes,
)
from app.core.errors import ErrorCode

# backend/tests/unit/test_capability_manifest.py -> parents[3] is the repo
# root (Talviran/), same depth as every other path in this file's own
# directory.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_EVIDENCE_SERVICE_PATH = _REPO_ROOT / "backend" / "app" / "modules" / "evidence" / "service.py"
_GLOBAL_ASSETS_TS_PATH = _REPO_ROOT / "frontend" / "src" / "data" / "globalAssets.ts"


def test_no_duplicate_asset_classes() -> None:
    names = [e.asset_class for e in CAPABILITY_MANIFEST]
    assert len(names) == len(set(names))


def test_unsupported_entries_claim_nothing() -> None:
    for entry in CAPABILITY_MANIFEST:
        if entry.reason is not None:
            assert not entry.price
            assert not entry.chart
            assert not entry.compare
            assert not entry.monitor
            assert not entry.export
            assert entry.metric_ids == ()
            assert isinstance(entry.reason, ErrorCode)


def test_supported_entries_have_no_reason_code() -> None:
    for entry in CAPABILITY_MANIFEST:
        if entry.reason is None:
            assert entry.price or entry.chart, (
                f"{entry.asset_class} has no reason code but claims nothing either"
            )


def test_get_capability_lookup() -> None:
    gilts = get_capability("UK gilts")
    assert gilts is not None
    assert gilts.reason is None
    assert "UK_GILT_NOMINAL_SPOT_CURVE" in gilts.metric_ids

    assert get_capability("nonexistent asset class") is None


def test_supported_vs_unsupported_partition_is_total() -> None:
    supported = set(supported_asset_classes())
    unsupported = set(unsupported_asset_classes())
    assert supported.isdisjoint(unsupported)
    assert supported | unsupported == {e.asset_class for e in CAPABILITY_MANIFEST}


def test_only_uk_gilts_are_monitor_capable_today() -> None:
    """Ground-truthed against monitoring/rule_engine.py's SCALAR_VALUE_KEYS /
    CALCULATION_SCALAR_VALUE_KEYS registries (both contain exactly one
    metric_id each, both UK-gilt-specific) - not assumed parity across
    asset classes. If this starts failing, either the manifest or
    rule_engine.py's registries have drifted from each other; re-check both
    before editing either."""
    monitor_capable = [e.asset_class for e in CAPABILITY_MANIFEST if e.monitor]
    assert monitor_capable == ["UK gilts"]


# --- Cross-check #1: evidence/service.py's real refusal guards -------------


def test_unsupported_entries_match_evidence_service_guards() -> None:
    """Every asset_class this manifest marks unsupported must be a literal
    `asset_class="..."` string evidence/service.py actually passes to
    `_not_yet_connected_reply` - read from the real file, not copied by
    hand, so this fails the moment the two drift apart."""
    assert _EVIDENCE_SERVICE_PATH.is_file(), (
        f"expected evidence/service.py at {_EVIDENCE_SERVICE_PATH}"
    )
    source = _EVIDENCE_SERVICE_PATH.read_text(encoding="utf-8")
    guarded_classes = set(
        re.findall(r'_not_yet_connected_reply\(\s*[^)]*?asset_class="([^"]+)"', source)
    )
    assert guarded_classes, "no _not_yet_connected_reply(asset_class=...) calls found at all"

    manifest_unsupported = set(unsupported_asset_classes())
    # Every manifest "unsupported" entry must correspond to a real guard...
    assert manifest_unsupported <= guarded_classes, (
        f"manifest claims unsupported for classes with no real guard: "
        f"{manifest_unsupported - guarded_classes}"
    )
    # ...and every real guard should be represented in the manifest, so the
    # manifest can't silently go stale as new guards are added.
    assert guarded_classes <= manifest_unsupported, (
        f"evidence/service.py refuses these asset classes but the manifest "
        f"doesn't document them: {guarded_classes - manifest_unsupported}"
    )


# --- Cross-check #2: frontend's VERIFIED_LIVE_SYMBOLS -----------------------

# Equities are the one place this manifest's symbols (real identity-
# resolution aliases, "{EXCHANGE}:{SYMBOL}") and the frontend's
# VERIFIED_LIVE_SYMBOLS (display tickers, LSE-style for two of the five
# pilot names) use genuinely different notations for the same underlying
# security - this is a real, pre-existing inconsistency between the two
# scattered mechanisms, not a bug in this test. Documented explicitly so it
# can't silently get worse (or silently get "fixed" without anyone
# noticing - if frontend ever adds 'VOD' or renames 'BP.L'/'AZN.L', this
# assertion starts failing and must be revisited, not loosened blindly).
_KNOWN_EQUITY_NOTATION_MAP = {
    "NASDAQ:AAPL": "AAPL",
    "NASDAQ:MSFT": "MSFT",
}
_KNOWN_FRONTEND_GAPS_FOR_PILOT_EQUITIES = {
    # backend alias -> why it has no clean frontend counterpart today
    "NASDAQ:VOD": "Vodafone isn't in VERIFIED_LIVE_SYMBOLS under any spelling.",
    "NYSE:BP": (
        "frontend lists 'BP.L' (LSE), an ADR ticker, not the NYSE ADR alias "
        "the backend's PILOT_EQUITIES/equity_ingest.py actually ingest."
    ),
    "NASDAQ:AZN": (
        "frontend lists 'AZN.L' (LSE), not the NASDAQ ADR alias the "
        "backend's PILOT_EQUITIES/equity_ingest.py actually ingest."
    ),
}


def _read_frontend_verified_live_symbols() -> set[str]:
    assert _GLOBAL_ASSETS_TS_PATH.is_file(), (
        f"expected frontend/src/data/globalAssets.ts at {_GLOBAL_ASSETS_TS_PATH}"
    )
    source = _GLOBAL_ASSETS_TS_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"VERIFIED_LIVE_SYMBOLS[^=]*=\s*new Set\(\[(.*?)\]\)", source, re.DOTALL
    )
    assert match is not None, "VERIFIED_LIVE_SYMBOLS set literal not found - has it moved/renamed?"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_fx_symbol_is_in_frontend_verified_live_set() -> None:
    """The one case with zero notation ambiguity: 'GBP/USD' is spelled
    identically in both layers."""
    frontend_symbols = _read_frontend_verified_live_symbols()
    assert "GBP/USD" in frontend_symbols
    assert "GBP/USD" in all_supported_symbols()


def test_equity_symbols_partially_cross_reference_frontend() -> None:
    frontend_symbols = _read_frontend_verified_live_symbols()
    equities_entry = get_capability("US equities (pilot list)")
    assert equities_entry is not None

    for backend_alias, frontend_ticker in _KNOWN_EQUITY_NOTATION_MAP.items():
        assert backend_alias in equities_entry.symbols
        assert frontend_ticker in frontend_symbols, (
            f"{backend_alias} should map to {frontend_ticker!r} in "
            "VERIFIED_LIVE_SYMBOLS, but it's missing - either the frontend "
            "list changed or this mapping is stale"
        )

    # The known gaps: assert they're STILL gaps, so this test fails loudly
    # (telling someone to update it) the day the frontend list is fixed to
    # cover Vodafone/BP/AstraZeneca under a reconcilable spelling.
    for backend_alias in _KNOWN_FRONTEND_GAPS_FOR_PILOT_EQUITIES:
        assert backend_alias in equities_entry.symbols
        bare_ticker = backend_alias.split(":", 1)[1]
        # Neither the bare backend ticker nor its ".L" (LSE) spelling is an
        # exact match for what the backend actually ingests under this
        # alias: VOD isn't in the frontend list under any spelling; BP/AZN
        # ARE present as 'BP.L'/'AZN.L', but that's a *different* listing
        # (LSE ordinary shares) from the NYSE/NASDAQ ADR alias the backend
        # ingestion pipeline resolves identity against - a real symbol-
        # format mismatch, not the same instrument spelled two ways.
        assert bare_ticker not in frontend_symbols


@pytest.mark.parametrize(
    "backend_alias,reason", sorted(_KNOWN_FRONTEND_GAPS_FOR_PILOT_EQUITIES.items())
)
def test_known_equity_frontend_gap_is_explained(backend_alias: str, reason: str) -> None:
    """One assertion per documented gap so a test report lists each by name
    instead of one opaque combined failure."""
    assert reason  # non-empty - this is a documentation test, not a logic one
