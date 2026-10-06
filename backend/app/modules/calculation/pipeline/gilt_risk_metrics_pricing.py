"""Persists calculation.calculation_result rows for gilt_risk_metrics_v1 —
mirrors curve_pricing.py's shape (the only other wired calc spec) exactly:
read inputs from market.accepted_fact only, gate on the spec being
APPROVED, compute, persist, record CalculationInput lineage, supersede the
prior ACTIVE result if the value actually changed.

Scope, deliberately narrower than the full TAL-FI-GILT-001 methodology
(docs/Talvrin_Gilt_Analytics_Methodology_Decision.docx) for this first
wiring pass: **cum-dividend settlements only**. No ex-dividend-period
detection from real calendar dates exists anywhere in this codebase yet
(every existing caller of gilt_price_yield_v1 either assumes cum-dividend
or requires the caller to already know the ex-dividend state) — building a
correct UK-gilt ex-dividend business-day window is new, non-trivial
calendar logic, not a mechanical wiring step, so it's out of scope here.
This mirrors gilt_price_from_curve_v1/implementation.py's own identical,
already-documented "cum-dividend only" limitation — not a new gap.

The source yield (GILT_MARKET_CLOSE_PRICE's own `yield_pct` field,
supplied directly by Tradeweb) is deliberately never used in the
calculation — TAL-FI-GILT-001 Table 10 is explicit: "Solve the DMO
dirty-price equation from the observed clean price and derived accrued
interest. The source yield is never mixed into the production
calculation." Only the clean price is treated as the market observation;
everything else is re-derived from it under the pinned DMO convention.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    BASIS_OBSERVED_YIELD_DERIVED,
    STATUS_APPROVED,
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
    CalculationSupersession,
)
from app.modules.calculation.specs.gilt_price_yield_v1.implementation import (
    accrued_interest,
    yield_from_price,
)
from app.modules.calculation.specs.gilt_price_yield_v1.schedule import (
    standard_inputs_from_dates,
    timeline_for_settlement,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.evidence import (
    METHODOLOGY_VERSION,
    ConventionDerivedInputs,
    InstrumentMaster,
    MethodMetadata,
    ObservedInput,
    RightsContext,
    TemporalLineage,
    build_evidence_bundle,
    bundle_to_jsonable,
)
from app.modules.calculation.specs.gilt_risk_metrics_v1.status import (
    RiskMetricsOutcome,
    RiskMetricsStatus,
    compute_risk_metrics_outcome,
)
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.market.pipeline.tradeweb_price_ingest import METRIC_GILT_MARKET_CLOSE_PRICE
from app.modules.market.queries import current_accepted_fact_at
from app.modules.reference.models import InstrumentAlias

#: TAL-FI-GILT-001 Table 19's metric_id for this bundled result - one row
#: per (instrument, as_of_date) holding all four metrics + status, the
#: same "one coherent calculation output, not one row per number"
#: convention curve_pricing.py's own MODEL_IMPLIED_CLEAN_PRICE already
#: established for this codebase.
METRIC_GILT_RISK_METRICS = "GILT_RISK_METRICS"

#: Rounding/display-precision version tag (TAL-FI-GILT-001 Table 11) -
#: versioned here, not hard-coded per call site, so a future rounding
#: convention change is a one-line bump, matching every other versioned
#: constant in this spec (BUMP_SIZE, METHODOLOGY_VERSION).
ROUNDING_VERSION = "display-v1"


@dataclass(frozen=True)
class GiltRiskMetricsSkipped:
    reason: str


@dataclass(frozen=True)
class GiltRiskMetricsComputed:
    calculation_result_id: uuid.UUID
    decision: str  # ACCEPTED | NO_CHANGE
    status: RiskMetricsStatus


async def _current_calculation_result(
    session: AsyncSession,
    *,
    calculation_specification_id: uuid.UUID,
    subject_id: uuid.UUID,
    metric_id: str,
    as_of_date: dt.date,
) -> CalculationResult | None:
    return (
        await session.execute(
            select(CalculationResult).where(
                CalculationResult.calculation_specification_id == calculation_specification_id,
                CalculationResult.subject_id == subject_id,
                CalculationResult.metric_id == metric_id,
                CalculationResult.as_of_date == as_of_date,
                CalculationResult.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()


async def _isin_for_instrument(session: AsyncSession, instrument_id: uuid.UUID) -> str | None:
    return (
        await session.execute(
            select(InstrumentAlias.alias_value).where(
                InstrumentAlias.instrument_id == instrument_id,
                InstrumentAlias.alias_type == "ISIN",
            )
        )
    ).scalar_one_or_none()


async def compute_and_persist_gilt_risk_metrics(
    session: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    as_of_date: dt.date,
    calculation_specification_id: uuid.UUID,
) -> GiltRiskMetricsComputed | GiltRiskMetricsSkipped:
    # Same reasoning as curve_pricing.py's identical check: a DRAFT spec
    # has not passed FIN-001's golden-test + dual-implementation gate, so
    # refusing to compute under it must happen before any computation, not
    # just before persistence.
    spec = await session.get(CalculationSpecification, calculation_specification_id)
    if spec is None or spec.status != STATUS_APPROVED:
        return GiltRiskMetricsSkipped(
            reason=(
                f"calculation_specification {calculation_specification_id} is not "
                f"APPROVED (status={spec.status if spec is not None else 'MISSING'}) - "
                "refusing to compute or persist a result under an unvetted methodology"
            )
        )

    at = dt.datetime.combine(as_of_date, dt.time.min, tzinfo=dt.UTC)

    reference_fact = await current_accepted_fact_at(
        session, subject_id=instrument_id, metric_id=METRIC_GILT_REFERENCE_TERMS, at=at
    )
    if reference_fact is None:
        return GiltRiskMetricsSkipped(
            reason=(
                f"no {METRIC_GILT_REFERENCE_TERMS} accepted_fact for instrument "
                f"{instrument_id} valid at {as_of_date}"
            )
        )

    price_fact = await current_accepted_fact_at(
        session, subject_id=instrument_id, metric_id=METRIC_GILT_MARKET_CLOSE_PRICE, at=at
    )
    if price_fact is None:
        return GiltRiskMetricsSkipped(
            reason=(
                f"no {METRIC_GILT_MARKET_CLOSE_PRICE} accepted_fact for instrument "
                f"{instrument_id} on {as_of_date}"
            )
        )

    isin = await _isin_for_instrument(session, instrument_id)
    if isin is None:
        return GiltRiskMetricsSkipped(
            reason=f"no ISIN alias registered for instrument {instrument_id}"
        )

    coupon_per_100 = Decimal(reference_fact.value["coupon_rate"])
    maturity_date = dt.date.fromisoformat(reference_fact.value["redemption_date"])
    issue_date = dt.date.fromisoformat(reference_fact.value["first_issue_date"])
    clean_price = Decimal(price_fact.value["clean_price"])
    gilt_type = reference_fact.value.get("gilt_type")

    # Table 13's "Ineligible structure" and "On/after redemption" rows -
    # both decidable here (gilt_type, maturity_date vs as_of_date) even
    # though status.py's own pure-math layer can't see either field. Both
    # still produce a persisted, evidenced result (status recorded, not a
    # bare skip) - "suppress the metric rather than estimate it", not
    # "pretend nothing happened".
    schedule_hash = ""
    accrued = Decimal(0)
    dirty_price = clean_price
    solved_yield = Decimal(0)
    if gilt_type != "CONVENTIONAL":
        outcome = RiskMetricsOutcome(
            status=RiskMetricsStatus.NOT_COVERED_BY_METHOD_V1, metrics=None
        )
    elif as_of_date >= maturity_date:
        outcome = RiskMetricsOutcome(status=RiskMetricsStatus.MATURED, metrics=None)
    else:
        # Cum-dividend only - see module docstring. standard_inputs_from_dates
        # itself documents this same assumption (d1=d2=coupon/f exactly).
        inputs = standard_inputs_from_dates(
            coupon_per_100=coupon_per_100, maturity_date=maturity_date, settlement_date=as_of_date
        )
        timeline = timeline_for_settlement(
            maturity_date=maturity_date, settlement_date=as_of_date
        )
        schedule_hash = str(timeline.remaining_quasi_coupon_dates)
        days_since_previous = (
            inputs.days_in_quasi_coupon_period - inputs.days_to_next_quasi_coupon
        )
        accrued = accrued_interest(
            next_cash_flow=inputs.next_cash_flow,
            days_since_previous_quasi_coupon=days_since_previous,
            days_in_quasi_coupon_period=inputs.days_in_quasi_coupon_period,
            settled_on_or_before_ex_dividend=True,  # cum-dividend only, see module docstring
        )
        dirty_price = clean_price + accrued

        try:
            solved_yield = yield_from_price(inputs, dirty_price)
        except ValueError as exc:
            return GiltRiskMetricsSkipped(reason=f"yield solve failed: {exc}")

        outcome = compute_risk_metrics_outcome(inputs, solved_yield)

    assert price_fact.knowledge_range.lower is not None  # our own rows always set this
    price_knowledge_time = price_fact.knowledge_range.lower

    bundle = build_evidence_bundle(
        metric_id=METRIC_GILT_RISK_METRICS,
        instrument_id=instrument_id,
        observed_input=ObservedInput(
            clean_price=clean_price,
            price_currency="GBP",
            source_dataset_id="tradeweb.gilt-closing-prices",
            source_record_id=str(price_fact.id),
            source_effective_at=at,
            source_published_at=price_knowledge_time,
        ),
        rights=RightsContext(
            rights_policy_id="tradeweb.gilt-prices",
            entitlement_class="internal-dev",
            export_allowed=False,
            redistribution_allowed=False,
        ),
        instrument_master=InstrumentMaster(
            isin=isin,
            coupon=coupon_per_100,
            issue_date=issue_date,
            maturity_date=maturity_date,
            first_dividend_attributes=None,  # cum-dividend-only scope, see module docstring
            master_data_source_id="reference.instrument",
            master_snapshot_hash=str(reference_fact.id),
        ),
        convention=ConventionDerivedInputs(
            settlement_date=as_of_date,
            calendar_version="uk-gilt-settlement-v1",
            ex_dividend_state=False,  # cum-dividend-only scope, see module docstring
            accrued_interest=accrued,
            dirty_price=dirty_price,
            solved_yield=solved_yield,
            cashflow_schedule_hash=schedule_hash,
        ),
        method=MethodMetadata(
            dmo_document_edition="4th edition, 18 Dec 2024",
            dmo_document_hash="",
            engine_build_hash="",
            calculation_config_hash=METHODOLOGY_VERSION,
        ),
        temporal=TemporalLineage(
            market_valid_time=at,
            knowledge_time=price_knowledge_time,
            ingested_at=price_knowledge_time,
            calculated_at=dt.datetime.now(dt.UTC),
        ),
        risk_metrics=outcome.metrics,
        calculation_status=outcome.status,
        rounding_version=ROUNDING_VERSION,
    )
    value = bundle_to_jsonable(bundle)

    existing = await _current_calculation_result(
        session,
        calculation_specification_id=calculation_specification_id,
        subject_id=instrument_id,
        metric_id=METRIC_GILT_RISK_METRICS,
        as_of_date=as_of_date,
    )

    # evidence_bundle_id/calculated_at/source_record_id (price_fact.id is
    # stable, but a fresh bundle_id and calculated_at timestamp are
    # generated every call) always differ between runs, so compare on the
    # actual numeric/status content only, not the whole dict.
    def _content(v: dict[str, object]) -> object:
        outputs = v.get("outputs", {})
        return (v.get("convention"), outputs)

    if existing is not None and _content(existing.value) == _content(value):
        return GiltRiskMetricsComputed(
            calculation_result_id=existing.id, decision="NO_CHANGE", status=outcome.status
        )

    new_result = CalculationResult(
        calculation_specification_id=calculation_specification_id,
        subject_type="INSTRUMENT",
        subject_id=instrument_id,
        metric_id=METRIC_GILT_RISK_METRICS,
        as_of_date=as_of_date,
        basis=BASIS_OBSERVED_YIELD_DERIVED,
        value=value,
        status="ACTIVE",
    )
    session.add(new_result)
    await session.flush()

    session.add(
        CalculationInput(
            calculation_result_id=new_result.id,
            accepted_fact_id=reference_fact.id,
            role="REFERENCE_TERMS",
        )
    )
    session.add(
        CalculationInput(
            calculation_result_id=new_result.id,
            accepted_fact_id=price_fact.id,
            role="OBSERVED_PRICE",
        )
    )

    if existing is not None:
        existing.status = "SUPERSEDED"
        existing.superseded_by_id = new_result.id
        session.add(
            CalculationSupersession(
                old_calculation_result_id=existing.id,
                new_calculation_result_id=new_result.id,
                reason="recalculated: inputs changed since the last result for this date",
            )
        )

    return GiltRiskMetricsComputed(
        calculation_result_id=new_result.id, decision="ACCEPTED", status=outcome.status
    )
