"""Unit tests for the materiality classifier (PRD roadmap item #3) — pure
logic, no DB dependency, proving the "works independently of the LLM"
requirement: every branch here is plain arithmetic/string formatting.
"""

from decimal import Decimal

from app.modules.market.materiality import (
    MODE_ANY_CHANGE,
    MODE_NUMERIC_THRESHOLD,
    MaterialityRule,
    classify_materiality,
)


def test_identical_values_are_never_material() -> None:
    is_material, explanation = classify_materiality({"a": "1"}, {"a": "1"}, rule=None)
    assert is_material is False
    assert explanation == "No change in value."


def test_no_rule_configured_defaults_to_material() -> None:
    is_material, explanation = classify_materiality({"a": "1"}, {"a": "2"}, rule=None)
    assert is_material is True
    assert "no materiality rule is configured" in explanation


def test_any_change_mode_is_always_material_and_names_the_fields() -> None:
    rule = MaterialityRule(metric_id="GILT_REFERENCE_TERMS", mode=MODE_ANY_CHANGE)
    is_material, explanation = classify_materiality(
        {"coupon_rate": "4.25", "redemption_date": "2036-03-07"},
        {"coupon_rate": "4.25", "redemption_date": "2036-09-07"},
        rule=rule,
    )
    assert is_material is True
    assert "redemption_date" in explanation
    assert "coupon_rate" not in explanation.split("(")[0]  # unchanged field not listed as changed


def test_numeric_threshold_below_threshold_is_not_material() -> None:
    rule = MaterialityRule(
        metric_id="UK_GILT_NOMINAL_SPOT_CURVE", mode=MODE_NUMERIC_THRESHOLD,
        compare_field="spot_rate_pct", threshold=Decimal("0.05"), relative=False,
    )
    is_material, explanation = classify_materiality(
        {"spot_rate_pct": "4.500000"}, {"spot_rate_pct": "4.520000"}, rule=rule,
    )
    assert is_material is False
    assert "within normal noise" in explanation


def test_numeric_threshold_above_threshold_is_material() -> None:
    rule = MaterialityRule(
        metric_id="UK_GILT_NOMINAL_SPOT_CURVE", mode=MODE_NUMERIC_THRESHOLD,
        compare_field="spot_rate_pct", threshold=Decimal("0.05"), relative=False,
    )
    is_material, explanation = classify_materiality(
        {"spot_rate_pct": "4.500000"}, {"spot_rate_pct": "4.600000"}, rule=rule,
    )
    assert is_material is True
    assert "material" in explanation


def test_relative_threshold_below_is_not_material() -> None:
    rule = MaterialityRule(
        metric_id="FX_SPOT_RATE", mode=MODE_NUMERIC_THRESHOLD,
        compare_field="rate", threshold=Decimal("0.005"), relative=True,
    )
    is_material, _ = classify_materiality({"rate": "1.3000"}, {"rate": "1.3030"}, rule=rule)
    assert is_material is False


def test_relative_threshold_above_is_material() -> None:
    rule = MaterialityRule(
        metric_id="FX_SPOT_RATE", mode=MODE_NUMERIC_THRESHOLD,
        compare_field="rate", threshold=Decimal("0.005"), relative=True,
    )
    is_material, explanation = classify_materiality(
        {"rate": "1.3000"}, {"rate": "1.3100"}, rule=rule
    )
    assert is_material is True
    assert "relative" in explanation


def test_relative_threshold_from_zero_is_always_material() -> None:
    rule = MaterialityRule(
        metric_id="FX_SPOT_RATE", mode=MODE_NUMERIC_THRESHOLD,
        compare_field="rate", threshold=Decimal("0.005"), relative=True,
    )
    is_material, explanation = classify_materiality({"rate": "0"}, {"rate": "1.31"}, rule=rule)
    assert is_material is True
    assert "moved from 0" in explanation


def test_non_numeric_field_change_is_treated_as_material() -> None:
    rule = MaterialityRule(
        metric_id="UK_GILT_NOMINAL_SPOT_CURVE", mode=MODE_NUMERIC_THRESHOLD,
        compare_field="spot_rate_pct", threshold=Decimal("0.05"), relative=False,
    )
    is_material, explanation = classify_materiality(
        {"spot_rate_pct": "not-a-number"}, {"spot_rate_pct": "4.6"}, rule=rule,
    )
    assert is_material is True
    assert "could not be compared numerically" in explanation
