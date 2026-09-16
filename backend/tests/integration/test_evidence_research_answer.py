"""assemble_research_answer against real Postgres: each of the five
branches, the PDP gate actually blocking when a capability is unregistered,
and the gilt-facts/yield-curve branches pulling real accepted_fact/
calculation_result rows (never fabricated ones) with correct labeling.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import (
    BASIS_MODEL_IMPLIED,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.evidence.models import EvidenceBundle
from app.modules.evidence.service import SEED_GILT_ISIN, assemble_research_answer
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer
from app.modules.rights.models import RightsGrant, RightsProfile

_OPEN_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2003, 2, 27, tzinfo=dt.UTC), upper=None, bounds="[)"
)
_CURVE_DAY_RANGE: Range[dt.datetime] = Range(
    lower=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
    upper=dt.datetime(2026, 9, 15, tzinfo=dt.UTC),
    bounds="[)",
)


async def _seed_capability_and_jurisdiction(session: AsyncSession) -> None:
    session.add(
        CapabilityStatus(
            capability_code="research.answer", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    session.add(
        ActivationRecord(
            jurisdiction_code="GB",
            operating_entity="Test Entity",
            status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1),
            effective_to=None,
        )
    )
    await session.flush()


async def _seed_rights_profile(
    session: AsyncSession, *, code: str, actions: list[str]
) -> uuid.UUID:
    profile = RightsProfile(code=code, status="ACTIVE")
    session.add(profile)
    await session.flush()
    for action in actions:
        session.add(
            RightsGrant(rights_profile_id=profile.id, action=action, permission_state="ALLOW")
        )
    await session.flush()
    return profile.id


async def _seed_gilt(session: AsyncSession) -> Instrument:
    issuer = Issuer(name="HM Treasury", country_code="GB", status="ACTIVE")
    session.add(issuer)
    await session.flush()
    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN",
        name="4 1/4% Treasury Stock 2036", currency_code="GBP", status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()
    session.add(
        InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=SEED_GILT_ISIN)
    )
    await session.flush()
    return instrument


async def _seed_reference_fact(session: AsyncSession, instrument_id: uuid.UUID) -> None:
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT", subject_id=instrument_id,
            metric_id=METRIC_GILT_REFERENCE_TERMS, valid_range=_OPEN_RANGE,
            knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
            value={
                "instrument_name": "4 1/4% Treasury Stock 2036",
                "gilt_type": "CONVENTIONAL", "coupon_rate": "4.25",
                "redemption_date": "2036-03-07", "first_issue_date": "2003-02-27",
                "dividend_dates": "07-Mar and 07-Sep",
            },
            status="ACTIVE",
        )
    )
    await session.flush()


async def _seed_curve_points(session: AsyncSession, tenor_to_rate: dict[str, str]) -> None:
    for tenor, rate in tenor_to_rate.items():
        session.add(
            AcceptedFact(
                subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
                subject_id=curve_point_subject_id(Decimal(tenor)),
                metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                valid_range=_CURVE_DAY_RANGE,
                knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
                value={"tenor_years": tenor, "spot_rate_pct": rate},
                status="ACTIVE",
            )
        )
    await session.flush()


async def _seed_model_implied_price(session: AsyncSession, instrument_id: uuid.UUID) -> None:
    spec = CalculationSpecification(
        code=f"test-spec-{uuid.uuid4().hex[:8]}", version="1", status="DRAFT",
        description="test",
    )
    session.add(spec)
    await session.flush()
    session.add(
        CalculationResult(
            calculation_specification_id=spec.id,
            subject_type="INSTRUMENT", subject_id=instrument_id,
            metric_id=METRIC_MODEL_IMPLIED_CLEAN_PRICE, as_of_date=dt.date(2026, 9, 14),
            basis=BASIS_MODEL_IMPLIED,
            value={"dirty_price": "92.44", "accrued_interest": "0.08", "clean_price": "92.36"},
            status="ACTIVE",
        )
    )
    await session.flush()


async def test_advice_query_is_redirected(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    answer = await assemble_research_answer(
        db_session, query_text="should I buy this gilt?",
        principal_id=None, account_id=None,
    )
    assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION
    assert "can't tell you whether to buy" in answer.text
    assert answer.evidence_bundle_id is None


async def test_accrued_query_returns_explanation(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    answer = await assemble_research_answer(
        db_session, query_text="what is accrued interest?",
        principal_id=None, account_id=None,
    )
    assert answer.allowed_output_type == AllowedOutputType.DOCUMENT_EXPLANATION
    assert "Accrued interest" in answer.text
    assert len(answer.citations) == 1
    assert answer.citations[0].pill == "SOURCE"


async def test_default_query_has_no_facts(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    answer = await assemble_research_answer(
        db_session, query_text="what's the capital of France?",
        principal_id=None, account_id=None,
    )
    assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION
    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def test_gilt_query_returns_real_facts_and_model_price(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, instrument.id)
    await _seed_model_implied_price(db_session, instrument.id)
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])
    await _seed_rights_profile(db_session, code="boe.yield-curve", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="tell me about the 2036 gilt",
        principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.FACTUAL_EVIDENCE
    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["ISIN"] == SEED_GILT_ISIN
    assert "Model-implied clean price (estimate)" in rows
    assert rows["Model-implied clean price (estimate)"] == "92.36"

    labels = [c.label for c in answer.citations]
    assert any("Talvrin model estimate" in label for label in labels), (
        "the model-implied price must be labeled as an estimate, never as a market quote"
    )

    assert answer.evidence_bundle_id is not None
    bundle = await db_session.get(EvidenceBundle, answer.evidence_bundle_id)
    assert bundle is not None
    assert bundle.status == "ASSEMBLING"  # not READY until the caller links a message


async def test_gilt_query_without_display_rights_falls_back(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, instrument.id)
    # No RightsGrant at all for "uk-dmo.gilts" -> fail-closed DENY on display.

    answer = await assemble_research_answer(
        db_session, query_text="tell me about the 2036 gilt",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def test_pdp_denies_when_capability_is_unregistered(db_session: AsyncSession) -> None:
    # Deliberately skip _seed_capability_and_jurisdiction - fail-closed DENY.
    answer = await assemble_research_answer(
        db_session, query_text="what's the capital of France?",
        principal_id=None, account_id=None,
    )
    assert "not currently permitted" in answer.text
    assert answer.evidence_bundle_id is None


_CURVE_FIXTURE = {"1": "4.0", "2": "4.2", "5": "4.5", "10": "5.2", "20": "5.5", "30": "5.6"}


async def test_yield_curve_query_returns_real_curve_points(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_curve_points(db_session, _CURVE_FIXTURE)
    await _seed_rights_profile(db_session, code="boe.yield-curve", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="what's the current UK yield curve?",
        principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.FACTUAL_EVIDENCE
    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows == {
        "1Y": "4.0%", "2Y": "4.2%", "5Y": "4.5%",
        "10Y": "5.2%", "20Y": "5.5%", "30Y": "5.6%",
    }
    assert len(answer.citations) == 1
    assert answer.citations[0].label == "Bank of England — daily nominal gilt spot curve"
    assert answer.citations[0].pill == "CURRENT", "these are real published facts, not an estimate"
    assert answer.evidence_bundle_id is not None


async def test_yield_curve_query_takes_priority_over_gilt_facts(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, instrument.id)
    await _seed_curve_points(db_session, _CURVE_FIXTURE)
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])
    await _seed_rights_profile(db_session, code="boe.yield-curve", actions=["display"])

    # Mentions both "gilt" and "yield curve" - the curve branch must win.
    answer = await assemble_research_answer(
        db_session, query_text="what's the yield curve for gilts?",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    assert answer.facts.title == "UK nominal gilt spot curve (Bank of England)"


async def test_yield_curve_query_without_display_rights_falls_back(
    db_session: AsyncSession,
) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_curve_points(db_session, _CURVE_FIXTURE)
    # No RightsGrant for "boe.yield-curve" -> fail-closed DENY on display.

    answer = await assemble_research_answer(
        db_session, query_text="what's the yield curve today?",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def test_yield_curve_query_with_no_curve_data_falls_back(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="boe.yield-curve", actions=["display"])
    # No curve points seeded at all.

    answer = await assemble_research_answer(
        db_session, query_text="what's the yield curve today?",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None
