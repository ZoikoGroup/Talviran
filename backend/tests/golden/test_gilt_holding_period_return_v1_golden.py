"""FIN-001's golden-test gate for gilt_holding_period_return_v1 — hand-built
cases against the standard textbook holding-period-return definition (no
DMO source exists for returns — same documented gap gilt_risk_metrics_v1
already flags). golden/v1/corpus.json is versioned and never edited in
place.
"""

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.modules.calculation.golden_manifest import verify_corpus_integrity
from app.modules.calculation.specs.gilt_holding_period_return_v1.implementation import (
    HoldingPeriodInputs,
    compute_holding_period_return,
)
from app.modules.calculation.specs.gilt_holding_period_return_v1.shadow_implementation import (
    compute_holding_period_return as shadow_compute_holding_period_return,
)

CORPUS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "modules"
    / "calculation"
    / "specs"
    / "gilt_holding_period_return_v1"
    / "golden"
    / "v1"
)
CORPUS_PATH = CORPUS_DIR / "corpus.json"
CORPUS = json.loads(CORPUS_PATH.read_text())

_TOLERANCE = Decimal("1E-9")


def test_corpus_v1_bytes_have_not_silently_changed() -> None:
    verify_corpus_integrity(CORPUS_DIR)


def _inputs_from_case(case: dict[str, Any]) -> HoldingPeriodInputs:
    return HoldingPeriodInputs(
        coupon_per_100=Decimal(str(case["coupon_per_100"])),
        maturity_date=dt.date.fromisoformat(str(case["maturity_date"])),
        start_date=dt.date.fromisoformat(str(case["start_date"])),
        start_dirty_price=Decimal(str(case["start_dirty_price"])),
        end_date=dt.date.fromisoformat(str(case["end_date"])),
        end_dirty_price=Decimal(str(case["end_dirty_price"])),
    )


@pytest.mark.parametrize(
    "case", CORPUS["holding_period_return_cases"], ids=lambda c: c["id"]
)
def test_holding_period_return_matches_expected(case: dict[str, Any]) -> None:
    result = compute_holding_period_return(_inputs_from_case(case))
    assert result.coupon_payments_received == case["expected_coupon_payments_received"], case["id"]
    assert abs(result.income_received - Decimal(str(case["expected_income_received"]))) < _TOLERANCE
    assert abs(result.price_return - Decimal(str(case["expected_price_return"]))) < _TOLERANCE
    assert (
        abs(result.total_return_amount - Decimal(str(case["expected_total_return_amount"])))
        < _TOLERANCE
    )
    assert (
        abs(
            result.holding_period_return_pct
            - Decimal(str(case["expected_holding_period_return_pct"]))
        )
        < _TOLERANCE
    ), case["id"]


@pytest.mark.parametrize(
    "case", CORPUS["holding_period_return_cases"], ids=lambda c: c["id"]
)
def test_shadow_implementation_matches_expected(case: dict[str, Any]) -> None:
    """FIN-001's dual-implementation gate: the independently-derived
    (own coupon-schedule loop, ratio-based return formula) implementation
    must ALSO reproduce the expected values.
    """
    result = shadow_compute_holding_period_return(_inputs_from_case(case))
    assert result.coupon_payments_received == case["expected_coupon_payments_received"], case["id"]
    assert (
        abs(
            result.holding_period_return_pct
            - Decimal(str(case["expected_holding_period_return_pct"]))
        )
        < _TOLERANCE
    ), case["id"]


@pytest.mark.parametrize(
    "case", CORPUS["holding_period_return_cases"], ids=lambda c: c["id"]
)
def test_production_and_shadow_implementations_agree(case: dict[str, Any]) -> None:
    inputs = _inputs_from_case(case)
    production = compute_holding_period_return(inputs)
    shadow = shadow_compute_holding_period_return(inputs)
    assert production.coupon_payments_received == shadow.coupon_payments_received, case["id"]
    assert (
        abs(production.holding_period_return_pct - shadow.holding_period_return_pct)
        < Decimal("1E-20")
    ), case["id"]


def test_corpus_case_count_is_the_expected_5() -> None:
    assert len(CORPUS["holding_period_return_cases"]) == 5
