"""Proves gilt_risk_metrics_v1/evidence.py's build_evidence_bundle produces
a bundle matching TAL-FI-GILT-001 Table 19's field groups, for both a
normal (OK) outcome and a suppressed one - integrity hashes must still be
present and must change if the underlying inputs/outputs change, exactly
the "reproducibility, never silently overwrite" discipline FIN-001/§11 of
the methodology document both require.
"""

import datetime as dt
import uuid
from decimal import Decimal

from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    ConventionalGiltInputs,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.evidence import (
    ConventionDerivedInputs,
    InstrumentMaster,
    MethodMetadata,
    ObservedInput,
    RightsContext,
    TemporalLineage,
    build_evidence_bundle,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.status import (
    RiskMetricsStatus,
    compute_risk_metrics_outcome,
)

_NOW = dt.datetime(2026, 10, 6, 9, 0, tzinfo=dt.UTC)


def _example_context() -> dict[str, object]:
    """Synthetic but structurally realistic metadata - this calc spec has
    no real wiring to actual instrument/source/rights rows yet (see
    evidence.py's own docstring), so these are illustrative fixture values,
    not production data.
    """
    return dict(
        metric_id="FI.DURATION.MODIFIED",
        instrument_id=uuid.uuid4(),
        observed_input=ObservedInput(
            clean_price=Decimal("96.250"),
            price_currency="GBP",
            source_dataset_id="tradeweb.ftse-gilt-closing-prices",
            source_record_id="2026-10-06:GB00BDX8CX86",
            source_effective_at=_NOW,
            source_published_at=_NOW,
        ),
        rights=RightsContext(
            rights_policy_id="tradeweb.gilt-prices",
            entitlement_class="internal-qa",
            export_allowed=False,
            redistribution_allowed=False,
        ),
        instrument_master=InstrumentMaster(
            isin="GB00BDX8CX86",
            coupon=Decimal("8"),
            issue_date=dt.date(1992, 1, 1),
            maturity_date=dt.date(2015, 12, 7),
            first_dividend_attributes=None,
            master_data_source_id="reference.instrument",
            master_snapshot_hash="deadbeef" * 8,
        ),
        convention=ConventionDerivedInputs(
            settlement_date=dt.date(2026, 10, 7),
            calendar_version="uk-gilt-settlement-v1",
            ex_dividend_state=False,
            accrued_interest=Decimal("0.362637"),
            dirty_price=Decimal("96.612637"),
            solved_yield=Decimal("0.04445"),
            cashflow_schedule_hash="cafebabe" * 8,
        ),
        method=MethodMetadata(
            dmo_document_edition="4th edition, 18 Dec 2024",
            dmo_document_hash="0" * 64,
            engine_build_hash="1" * 40,
            calculation_config_hash="2" * 64,
        ),
        temporal=TemporalLineage(
            market_valid_time=_NOW,
            knowledge_time=_NOW,
            ingested_at=_NOW,
            calculated_at=_NOW,
        ),
        rounding_version="display-v1",
    )


def test_ok_outcome_produces_a_complete_bundle_with_full_precision_outputs() -> None:
    inputs = ConventionalGiltInputs(
        coupon_per_100=Decimal("8"),
        coupons_per_year=2,
        days_to_next_quasi_coupon=14,
        days_in_quasi_coupon_period=182,
        full_quasi_coupon_periods_remaining=33,
        next_cash_flow=Decimal("4"),
        next_but_one_cash_flow=Decimal("4"),
    )
    outcome = compute_risk_metrics_outcome(inputs, Decimal("0.04445"))
    assert outcome.status == RiskMetricsStatus.OK
    assert outcome.metrics is not None

    bundle = build_evidence_bundle(
        **_example_context(),
        risk_metrics=outcome.metrics,
        calculation_status=outcome.status,
    )

    assert bundle.outputs.calculation_status == RiskMetricsStatus.OK
    assert bundle.outputs.modified_duration_full == outcome.metrics.modified_duration
    assert bundle.outputs.macaulay_duration_full == outcome.metrics.macaulay_duration
    assert len(bundle.integrity.input_hash) == 64  # sha256 hex digest
    assert len(bundle.integrity.output_hash) == 64
    assert bundle.integrity.previous_bundle_id is None


def test_suppressed_outcome_still_produces_a_bundle_recording_the_status() -> None:
    """A suppressed calculation (Table 13) is a recorded outcome, not an
    absence of evidence - the bundle must exist and say why, with zeroed
    (not fabricated) output values.
    """
    inputs = ConventionalGiltInputs(
        coupon_per_100=Decimal("8"),
        coupons_per_year=2,
        days_to_next_quasi_coupon=14,
        days_in_quasi_coupon_period=182,
        full_quasi_coupon_periods_remaining=0,
        next_cash_flow=Decimal("0"),
        next_but_one_cash_flow=Decimal("4"),
    )
    outcome = compute_risk_metrics_outcome(inputs, Decimal("0.04445"))
    assert outcome.status == RiskMetricsStatus.UNAVAILABLE_FINAL_SETTLEMENT
    assert outcome.metrics is None

    bundle = build_evidence_bundle(
        **_example_context(),
        risk_metrics=outcome.metrics,
        calculation_status=outcome.status,
    )

    assert bundle.outputs.calculation_status == RiskMetricsStatus.UNAVAILABLE_FINAL_SETTLEMENT
    assert bundle.outputs.modified_duration_full == Decimal(0)
    assert len(bundle.integrity.output_hash) == 64


def test_integrity_hashes_change_when_inputs_differ() -> None:
    context_a = _example_context()
    context_b = _example_context()
    context_b["observed_input"] = ObservedInput(
        clean_price=Decimal("97.000"),  # different clean price
        price_currency="GBP",
        source_dataset_id="tradeweb.ftse-gilt-closing-prices",
        source_record_id="2026-10-06:GB00BDX8CX86",
        source_effective_at=_NOW,
        source_published_at=_NOW,
    )

    inputs = ConventionalGiltInputs(
        coupon_per_100=Decimal("8"),
        coupons_per_year=2,
        days_to_next_quasi_coupon=14,
        days_in_quasi_coupon_period=182,
        full_quasi_coupon_periods_remaining=33,
        next_cash_flow=Decimal("4"),
        next_but_one_cash_flow=Decimal("4"),
    )
    outcome = compute_risk_metrics_outcome(inputs, Decimal("0.04445"))

    bundle_a = build_evidence_bundle(
        **context_a, risk_metrics=outcome.metrics, calculation_status=outcome.status
    )
    bundle_b = build_evidence_bundle(
        **context_b, risk_metrics=outcome.metrics, calculation_status=outcome.status
    )

    assert bundle_a.integrity.input_hash != bundle_b.integrity.input_hash
    # outputs are identical (same computed metrics) - only the input hash differs
    assert bundle_a.integrity.output_hash == bundle_b.integrity.output_hash
