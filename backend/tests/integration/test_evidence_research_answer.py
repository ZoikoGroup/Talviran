"""assemble_research_answer against real Postgres: each of the five
branches, the PDP gate actually blocking when a capability is unregistered,
and the gilt-facts/yield-curve branches pulling real accepted_fact/
calculation_result rows (never fabricated ones) with correct labeling.
"""

import datetime as dt
import uuid
from decimal import Decimal
from unittest.mock import patch

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.calculation.models import (
    BASIS_MODEL_IMPLIED,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.evidence.models import (
    QUALITY_PASS,
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceBundle,
    ParsedDocumentVersion,
)
from app.modules.evidence.service import SEED_GILT_ISIN, assemble_research_answer
from app.modules.market.models import (
    AcceptedFact,
    Dataset,
    FactObservationLink,
    Source,
    SourceArtifact,
    SourceObservation,
)
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.market.pipeline.equity_ingest import METRIC_EQUITY_EOD_PRICE
from app.modules.market.pipeline.fx_ingest import METRIC_FX_SPOT_RATE, fx_pair_subject_id
from app.modules.market.pipeline.macro_ingest import macro_series_subject_id
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.market.pipeline.tradeweb_price_ingest import METRIC_GILT_MARKET_CLOSE_PRICE
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


async def _seed_accrued_document_chunk(
    session: AsyncSession,
    *,
    rights_profile_id: uuid.UUID,
    text_content: str = (
        "Calculating accrued interest for conventional gilts: the "
        "ex-dividend convention means accrued interest can go negative inside the "
        "ex-dividend window."
    ),
) -> Document:
    source = Source(code=f"test-source-{uuid.uuid4().hex[:8]}", name="Test Source")
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="methodology-docs", name="Methodology Docs")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_ref="test://fixture", media_type="application/pdf", byte_length=1,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()

    document = Document(title="UK DMO Worked Examples (test)", media_type="application/pdf")
    session.add(document)
    await session.flush()
    version = DocumentVersion(
        document_id=document.id, source_artifact_id=artifact.id,
        rights_profile_id=rights_profile_id, retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(version)
    await session.flush()
    parsed = ParsedDocumentVersion(
        document_version_id=version.id, parser_name="test", parser_version="1",
        parse_started_at=dt.datetime.now(dt.UTC), extraction_quality=QUALITY_PASS,
    )
    session.add(parsed)
    await session.flush()
    session.add(
        DocumentChunk(
            parsed_document_version_id=parsed.id, chunker_version="1", ordinal=0,
            page_start=5, text_content=text_content,
            content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        )
    )
    await session.flush()
    return document


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


async def _seed_another_gilt(
    session: AsyncSession, *, isin: str, name: str, redemption_date: str, coupon_rate: str,
) -> Instrument:
    """A second, independently-named/ISIN'd gilt - for exercising the
    multi-gilt resolution and disambiguation paths _gilt_facts_reply
    gained once scripts.onboard_all_gilts widened real coverage beyond
    the single seed instrument these other fixtures assume.
    """
    issuer = (
        await session.execute(select(Issuer).where(Issuer.name == "HM Treasury"))
    ).scalar_one_or_none()
    if issuer is None:
        issuer = Issuer(name="HM Treasury", country_code="GB", status="ACTIVE")
        session.add(issuer)
        await session.flush()
    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="FI_SOVEREIGN", name=name,
        currency_code="GBP", status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()
    session.add(InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=isin))
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT", subject_id=instrument.id,
            metric_id=METRIC_GILT_REFERENCE_TERMS, valid_range=_OPEN_RANGE,
            knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
            value={
                "instrument_name": name, "gilt_type": "CONVENTIONAL", "coupon_rate": coupon_rate,
                "redemption_date": redemption_date, "first_issue_date": "2020-01-01",
                "dividend_dates": "some dates",
            },
            status="ACTIVE",
        )
    )
    await session.flush()
    return instrument


async def _seed_reference_fact(
    session: AsyncSession, instrument_id: uuid.UUID, *, knowledge_time: dt.datetime | None = None
) -> None:
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT", subject_id=instrument_id,
            metric_id=METRIC_GILT_REFERENCE_TERMS, valid_range=_OPEN_RANGE,
            knowledge_range=Range(
                lower=knowledge_time or dt.datetime.now(dt.UTC), upper=None, bounds="[)"
            ),
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


async def _seed_curve_points(
    session: AsyncSession,
    tenor_to_rate: dict[str, str],
    *,
    knowledge_time: dt.datetime | None = None,
) -> None:
    for tenor, rate in tenor_to_rate.items():
        session.add(
            AcceptedFact(
                subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
                subject_id=curve_point_subject_id(Decimal(tenor)),
                metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                valid_range=_CURVE_DAY_RANGE,
                knowledge_range=Range(
                    lower=knowledge_time or dt.datetime.now(dt.UTC), upper=None, bounds="[)"
                ),
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


async def _seed_market_close_price(
    session: AsyncSession, instrument_id: uuid.UUID, *, knowledge_time: dt.datetime | None = None
) -> None:
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT", subject_id=instrument_id,
            metric_id=METRIC_GILT_MARKET_CLOSE_PRICE, valid_range=_CURVE_DAY_RANGE,
            knowledge_range=Range(
                lower=knowledge_time or dt.datetime.now(dt.UTC), upper=None, bounds="[)"
            ),
            value={
                "instrument_name": "4 1/4% Treasury Stock 2036",
                "instrument_type": "Conventional",
                "clean_price": "93.410", "dirty_price": "93.512",
                "yield_pct": "4.612", "mod_duration": "7.912",
                "accrued_interest": "0.102",
            },
            status="ACTIVE",
        )
    )
    await session.flush()


async def _seed_fx_fact(
    session: AsyncSession, *, rate: str = "1.3350", knowledge_time: dt.datetime | None = None
) -> AcceptedFact:
    fact = AcceptedFact(
        subject_type="FX_PAIR", subject_id=fx_pair_subject_id("GBP", "USD"),
        metric_id=METRIC_FX_SPOT_RATE, valid_range=_CURVE_DAY_RANGE,
        knowledge_range=Range(
            lower=knowledge_time or dt.datetime.now(dt.UTC), upper=None, bounds="[)"
        ),
        value={"base_currency": "GBP", "quote_currency": "USD", "rate": rate},
        status="ACTIVE",
    )
    session.add(fact)
    await session.flush()
    return fact


async def _link_fact_to_new_observation(
    session: AsyncSession, *, fact: AcceptedFact, rights_profile_id: uuid.UUID
) -> None:
    """A real observation, linked via FactObservationLink, backed by its
    own distinct rights_profile_id - the exact shape _confirming_source_
    count counts, mirroring how a real second source (e.g. boe) actually
    gets linked in production by reconcile.py.
    """
    source = Source(code=f"test-source-{uuid.uuid4().hex[:8]}", name="Test Source")
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="rates", name="Test Rates")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id, sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_ref="test://fx-fixture", media_type="application/json", byte_length=1,
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    observation = SourceObservation(
        source_artifact_id=artifact.id, rights_profile_id=rights_profile_id,
        subject_type=fact.subject_type, subject_id=fact.subject_id, metric_id=fact.metric_id,
        semantic_observation_key=str(uuid.uuid4()), raw_value=fact.value,
        observed_at=dt.datetime.now(dt.UTC),
    )
    session.add(observation)
    await session.flush()
    session.add(
        FactObservationLink(
            accepted_fact_id=fact.id, source_observation_id=observation.id, role="PRIMARY"
        )
    )
    await session.flush()


async def _seed_equity(
    session: AsyncSession, *, issuer_name: str, symbol: str, exchange: str = "NASDAQ",
) -> Instrument:
    issuer = Issuer(name=issuer_name, country_code="US", status="ACTIVE")
    session.add(issuer)
    await session.flush()
    instrument = Instrument(
        issuer_id=issuer.id, instrument_type="EQUITY_COMMON", name=issuer_name,
        currency_code="USD", status="ACTIVE",
    )
    session.add(instrument)
    await session.flush()
    session.add(
        InstrumentAlias(
            instrument_id=instrument.id, alias_type="TICKER", alias_value=f"{exchange}:{symbol}"
        )
    )
    await session.flush()
    return instrument


async def _seed_equity_fact(
    session: AsyncSession, *, instrument_id: uuid.UUID, close_price: str = "335.92",
    symbol: str = "AAPL", exchange: str = "NASDAQ", knowledge_time: dt.datetime | None = None,
) -> None:
    session.add(
        AcceptedFact(
            subject_type="INSTRUMENT", subject_id=instrument_id, metric_id=METRIC_EQUITY_EOD_PRICE,
            valid_range=_CURVE_DAY_RANGE,
            knowledge_range=Range(
                lower=knowledge_time or dt.datetime.now(dt.UTC), upper=None, bounds="[)"
            ),
            value={
                "symbol": symbol, "exchange": exchange, "close_price": close_price,
                "currency_code": "USD",
            },
            status="ACTIVE",
        )
    )
    await session.flush()


async def test_fx_query_returns_real_rate_confirmed_by_two_sources(
    db_session: AsyncSession,
) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    frankfurter_rights = await _seed_rights_profile(
        db_session, code="frankfurter.fx", actions=["display"]
    )
    boe_rights = await _seed_rights_profile(db_session, code="boe.fx-rates", actions=["display"])
    fact = await _seed_fx_fact(db_session)
    await _link_fact_to_new_observation(db_session, fact=fact, rights_profile_id=frankfurter_rights)
    await _link_fact_to_new_observation(db_session, fact=fact, rights_profile_id=boe_rights)

    answer = await assemble_research_answer(
        db_session, query_text="what is the gbp to usd exchange rate",
        principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.FACTUAL_EVIDENCE
    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["Spot rate"] == "1.3350"
    assert rows["Confirmed by"] == "2 independent sources"
    assert "2 independent sources" in answer.text
    assert answer.evidence_bundle_id is not None


async def test_fx_query_with_one_source_reports_singular(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    frankfurter_rights = await _seed_rights_profile(
        db_session, code="frankfurter.fx", actions=["display"]
    )
    fact = await _seed_fx_fact(db_session)
    await _link_fact_to_new_observation(db_session, fact=fact, rights_profile_id=frankfurter_rights)

    answer = await assemble_research_answer(
        db_session, query_text="exchange rate please", principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["Confirmed by"] == "1 independent source"


async def test_fx_query_without_display_rights_falls_back(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    fact = await _seed_fx_fact(db_session)
    profile_id = await _seed_rights_profile(
        db_session, code="frankfurter.fx", actions=["retrieve"]
    )
    await _link_fact_to_new_observation(db_session, fact=fact, rights_profile_id=profile_id)

    answer = await assemble_research_answer(
        db_session, query_text="what is the gbp usd exchange rate",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def test_fx_query_with_no_data_falls_back(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="frankfurter.fx", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="what is the gbp usd exchange rate",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def test_equity_query_matches_by_uppercase_ticker(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="twelve-data.equity", actions=["display"])
    instrument = await _seed_equity(db_session, issuer_name="Apple Inc.", symbol="AAPL")
    await _seed_equity_fact(db_session, instrument_id=instrument.id, close_price="335.92")

    answer = await assemble_research_answer(
        db_session, query_text="what's AAPL trading at", principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.FACTUAL_EVIDENCE
    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["Close price"] == "335.92 USD"
    assert rows["Ticker"] == "NASDAQ:AAPL"
    assert answer.evidence_bundle_id is not None


async def test_equity_query_matches_by_lowercase_company_name(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="twelve-data.equity", actions=["display"])
    instrument = await _seed_equity(db_session, issuer_name="Apple Inc.", symbol="AAPL")
    await _seed_equity_fact(db_session, instrument_id=instrument.id, close_price="335.92")

    answer = await assemble_research_answer(
        db_session, query_text="what's apple's stock price today",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    assert dict(answer.facts.rows)["Close price"] == "335.92 USD"


async def test_equity_query_bp_ticker_does_not_false_positive_on_basis_points(
    db_session: AsyncSession,
) -> None:
    """A real collision found while building this: "BP" is also common
    finance jargon for "basis points". Lowercase "bp" in that context must
    never be mistaken for the BP p.l.c. ticker - only exact-case "BP"
    should match.
    """
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="twelve-data.equity", actions=["display"])
    instrument = await _seed_equity(
        db_session, issuer_name="BP p.l.c.", symbol="BP", exchange="NYSE",
    )
    await _seed_equity_fact(
        db_session, instrument_id=instrument.id, close_price="35.10", symbol="BP", exchange="NYSE",
    )

    answer = await assemble_research_answer(
        db_session, query_text="what does a 10 bp move in yield mean",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None, "lowercase 'bp' jargon must not match the BP ticker"


async def test_equity_query_bp_uppercase_ticker_does_match(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="twelve-data.equity", actions=["display"])
    instrument = await _seed_equity(
        db_session, issuer_name="BP p.l.c.", symbol="BP", exchange="NYSE",
    )
    await _seed_equity_fact(
        db_session, instrument_id=instrument.id, close_price="35.10", symbol="BP", exchange="NYSE",
    )

    answer = await assemble_research_answer(
        db_session, query_text="what is BP's share price", principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    assert dict(answer.facts.rows)["Close price"] == "35.10 USD"


async def test_equity_query_with_no_company_mentioned_falls_through(
    db_session: AsyncSession,
) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="twelve-data.equity", actions=["display"])
    instrument = await _seed_equity(db_session, issuer_name="Apple Inc.", symbol="AAPL")
    await _seed_equity_fact(db_session, instrument_id=instrument.id)

    answer = await assemble_research_answer(
        db_session, query_text="what's the capital of France?",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION


async def test_equity_query_without_display_rights_falls_back(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="twelve-data.equity", actions=["retrieve"])
    instrument = await _seed_equity(db_session, issuer_name="Apple Inc.", symbol="AAPL")
    await _seed_equity_fact(db_session, instrument_id=instrument.id)

    answer = await assemble_research_answer(
        db_session, query_text="AAPL price", principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def _seed_macro_fact(
    session: AsyncSession, *, metric_id: str, series_code: str, period: str = "2023",
    value: str = "3340032380668.04", knowledge_time: dt.datetime | None = None,
) -> None:
    subject_id = macro_series_subject_id("WB", "WDI", series_code)
    period_start = dt.datetime(int(period), 1, 1, tzinfo=dt.UTC)
    period_end = dt.datetime(int(period) + 1, 1, 1, tzinfo=dt.UTC)
    session.add(
        AcceptedFact(
            subject_type="MACRO_SERIES", subject_id=subject_id, metric_id=metric_id,
            valid_range=Range(lower=period_start, upper=period_end, bounds="[)"),
            knowledge_range=Range(
                lower=knowledge_time or dt.datetime.now(dt.UTC), upper=None, bounds="[)"
            ),
            value={
                "provider_code": "WB", "dataset_code": "WDI", "series_code": series_code,
                "period": period, "value": value,
            },
            status="ACTIVE",
        )
    )
    await session.flush()


async def test_macro_gdp_query_for_uk_returns_real_value(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="dbnomics.macro", actions=["display"])
    await _seed_macro_fact(
        db_session, metric_id="MACRO_GDP", series_code="A-NY.GDP.MKTP.CD-GBR",
        period="2023", value="3340032380668.04",
    )

    answer = await assemble_research_answer(
        db_session, query_text="what is the UK's GDP", principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.FACTUAL_EVIDENCE
    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["Country"] == "United Kingdom"
    assert rows["Period"] == "2023"
    assert rows["Value"] == "$3,340,032,380,668"
    assert answer.evidence_bundle_id is not None


async def test_macro_cpi_query_for_usa_returns_real_value(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="dbnomics.macro", actions=["display"])
    await _seed_macro_fact(
        db_session, metric_id="MACRO_CPI", series_code="A-FP.CPI.TOTL.ZG-USA",
        period="2023", value="4.11633838374488",
    )

    answer = await assemble_research_answer(
        db_session, query_text="what's the inflation rate in america",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["Country"] == "United States"
    assert rows["Value"] == "4.12%"


async def test_macro_query_without_country_falls_through(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="dbnomics.macro", actions=["display"])
    await _seed_macro_fact(
        db_session, metric_id="MACRO_GDP", series_code="A-NY.GDP.MKTP.CD-GBR",
    )

    answer = await assemble_research_answer(
        db_session, query_text="what is GDP", principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION


async def test_macro_query_without_display_rights_falls_back(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="dbnomics.macro", actions=["retrieve"])
    await _seed_macro_fact(
        db_session, metric_id="MACRO_GDP", series_code="A-NY.GDP.MKTP.CD-GBR",
    )

    answer = await assemble_research_answer(
        db_session, query_text="what is the UK's GDP", principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def test_macro_query_with_no_data_falls_back(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_rights_profile(db_session, code="dbnomics.macro", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="what is the UK's GDP", principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None


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
    # No real document acquired/parsed in this test's DB - the static
    # fallback citation, not a real evidence bundle.
    assert answer.evidence_bundle_id is None


async def test_accrued_query_with_real_document_cites_real_evidence(
    db_session: AsyncSession,
) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    profile_id = await _seed_rights_profile(
        db_session, code="test.doc-display", actions=["display"]
    )
    document = await _seed_accrued_document_chunk(db_session, rights_profile_id=profile_id)

    answer = await assemble_research_answer(
        db_session, query_text="what is accrued interest?",
        principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.DOCUMENT_EXPLANATION
    assert answer.evidence_bundle_id is not None
    assert len(answer.citations) == 1
    assert answer.citations[0].label == document.title
    assert answer.citations[0].meta == "Page 5"

    bundle = await db_session.get(EvidenceBundle, answer.evidence_bundle_id)
    assert bundle is not None


async def test_accrued_query_without_display_rights_falls_back_to_static(
    db_session: AsyncSession,
) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    # Deliberately no "display" grant - rights denial, fail-closed.
    profile_id = await _seed_rights_profile(
        db_session, code="test.doc-no-display", actions=["store"]
    )
    await _seed_accrued_document_chunk(db_session, rights_profile_id=profile_id)

    answer = await assemble_research_answer(
        db_session, query_text="what is accrued interest?",
        principal_id=None, account_id=None,
    )

    assert answer.evidence_bundle_id is None
    assert answer.citations[0].label == "UK DMO — Gilt Formulae and Examples, 4th ed. Section Three"


async def test_catch_all_query_finds_real_document_evidence_via_lexical_fallback(
    db_session: AsyncSession,
) -> None:
    """No http client passed (http=None, the default) - the catch-all
    branch must still work via lexical-only search, never require Gemini.
    """
    await _seed_capability_and_jurisdiction(db_session)
    profile_id = await _seed_rights_profile(
        db_session, code="test.doc-display-2", actions=["display"]
    )
    document = await _seed_accrued_document_chunk(
        db_session, rights_profile_id=profile_id,
        text_content="The quasi-coupon schedule for a conventional gilt is built by "
        "counting back in exact half-year steps from the redemption date.",
    )

    answer = await assemble_research_answer(
        db_session, query_text="how is the quasi-coupon schedule built?",
        principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.DOCUMENT_EXPLANATION
    assert answer.evidence_bundle_id is not None
    assert answer.citations[0].label == document.title


async def test_catch_all_query_with_no_document_match_falls_back_to_default(
    db_session: AsyncSession,
) -> None:
    await _seed_capability_and_jurisdiction(db_session)

    answer = await assemble_research_answer(
        db_session, query_text="what's the weather like in London?",
        principal_id=None, account_id=None,
    )

    assert answer.evidence_bundle_id is None
    assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION


async def test_catch_all_query_degrades_to_lexical_when_gemini_call_fails(
    db_session: AsyncSession,
) -> None:
    """A broken/erroring Gemini call must never fail the whole request -
    it degrades to lexical search, same as if no http client were passed
    at all (GeminiEmbeddingError is caught, not propagated).

    Forces gemini_api_key to a fake truthy value via a patched Settings so
    the semantic attempt is always exercised regardless of whether the
    real environment happens to have GEMINI_API_KEY configured - this
    test's whole point is the failure-handling path, not the real key.
    """
    await _seed_capability_and_jurisdiction(db_session)
    profile_id = await _seed_rights_profile(
        db_session, code="test.doc-display-3", actions=["display"]
    )
    document = await _seed_accrued_document_chunk(
        db_session, rights_profile_id=profile_id,
        text_content="Long first dividend periods require a separate quasi-coupon "
        "schedule anchored to the irregular first coupon date.",
    )

    async def _broken_gemini(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    fake_settings = get_settings().model_copy(update={"gemini_api_key": "fake-test-key"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(_broken_gemini)) as http:
        with patch("app.modules.evidence.service.get_settings", return_value=fake_settings):
            answer = await assemble_research_answer(
                db_session, query_text="what is a long first dividend schedule?",
                principal_id=None, account_id=None, http=http,
            )

    assert answer.evidence_bundle_id is not None
    assert answer.citations[0].label == document.title


async def test_typo_glit_routes_to_gilt_facts_not_document_search(
    db_session: AsyncSession,
) -> None:
    # Real bug found live: "glit" (a real typo for "gilt": "todays uk glit
    # closing prices") didn't match _GILT_PATTERN, so a genuine live-price
    # question fell through to the document-search catch-all instead of
    # _gilt_facts_reply - landing on an unrelated DMO worked-example table
    # instead of real data, a materially wrong answer, not just a miss.
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, instrument.id)
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="todays uk glit closing prices",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    assert dict(answer.facts.rows)["ISIN"] == SEED_GILT_ISIN


async def test_catch_all_query_with_a_dense_numeric_chunk_is_not_dumped_raw(
    db_session: AsyncSession,
) -> None:
    # Real bug found live: a genuine, honestly-cited excerpt match (a DMO
    # worked-example table - dates/decimals packed one row per line) got
    # dumped verbatim into the chat reply. Real source, real citation, but
    # unreadable and unprofessional - the fix points at the citation
    # instead of inlining dense tabular text.
    await _seed_capability_and_jurisdiction(db_session)
    profile_id = await _seed_rights_profile(
        db_session, code="test.doc-display-table", actions=["display"]
    )
    dense_text = (
        "Scenario 1 2 3 4\nYield 0.04445 0.04445 0.04445 0.04445\n"
        "Settlement date 24-May-99 26-May-99 27-May-99 07-Jun-99\n"
        "Dirty Price 145.012268 145.047301 141.070132 141.257676"
    )
    document = await _seed_accrued_document_chunk(
        db_session, rights_profile_id=profile_id, text_content=dense_text,
    )

    answer = await assemble_research_answer(
        db_session, query_text="what is the settlement date scenario",
        principal_id=None, account_id=None,
    )

    assert answer.evidence_bundle_id is not None
    assert answer.citations[0].label == document.title
    assert dense_text not in answer.text
    assert "not something I can read out cleanly" in answer.text


async def test_default_query_has_no_facts(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    answer = await assemble_research_answer(
        db_session, query_text="what's the capital of France?",
        principal_id=None, account_id=None,
    )
    assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION
    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def test_market_maker_question_reaches_document_search_not_instrument_facts(
    db_session: AsyncSession,
) -> None:
    """Found live 2026-09-23: "Gilt-Edged Market Maker" contains the
    substring "gilt", so without _MARKET_STRUCTURE_PATTERN being checked
    first, this silently misrouted to the single-instrument facts branch
    and never reached the document corpus that actually answers it (the
    GEMM Guidebook, added the same day).
    """
    await _seed_capability_and_jurisdiction(db_session)
    profile_id = await _seed_rights_profile(
        db_session, code="test.doc-display-gemm", actions=["display"]
    )
    document = await _seed_accrued_document_chunk(
        db_session, rights_profile_id=profile_id,
        text_content="GEMM Criteria, Obligations and Privileges: GEMMs are committed to make "
        "continuous bid and offer prices to their clients in all gilts in which they are "
        "recognised as a market maker.",
    )

    # No hyphenated "gilt-edged" here - plainto_tsquery tokenizes it into
    # two lexemes ("gilt", "edged"), and the seeded chunk above doesn't
    # contain "edged", so an AND-match would fail for a reason unrelated
    # to what this test actually verifies (routing, not lexical parsing
    # of compound words).
    answer = await assemble_research_answer(
        db_session, query_text="obligations of a gilt market maker",
        principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.DOCUMENT_EXPLANATION
    assert answer.citations and answer.citations[0].label == document.title
    # The instrument-facts branch never even considered - no seed gilt
    # was registered in this test's DB at all, so a misroute there would
    # have surfaced as the "no data" default, not a document citation.


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


async def test_gilt_query_returns_real_market_price(db_session: AsyncSession) -> None:
    # A genuine Tradeweb quote is a distinct fact from the model-implied
    # estimate above - must appear as its own row, labeled as a real
    # quote (never conflated with the "not a market quote" model row).
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, instrument.id)
    await _seed_market_close_price(db_session, instrument.id)
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])
    await _seed_rights_profile(db_session, code="tradeweb.gilt-prices", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="tell me about the 2036 gilt",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["Market close price (Tradeweb — real quote)"] == "93.41"

    market_citation = next(c for c in answer.citations if "Tradeweb" in c.label)
    assert market_citation.meta is not None
    assert "real market quote" in market_citation.meta
    assert market_citation.pill == "CURRENT"


async def test_gilt_query_without_tradeweb_rights_omits_market_price(
    db_session: AsyncSession,
) -> None:
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, instrument.id)
    await _seed_market_close_price(db_session, instrument.id)
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])
    # deliberately no tradeweb.gilt-prices rights profile seeded

    answer = await assemble_research_answer(
        db_session, query_text="tell me about the 2036 gilt",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    assert "Market close price (Tradeweb — real quote)" not in dict(answer.facts.rows)


async def test_gilt_query_pill_reflects_real_fact_age_not_hardcoded_current(
    db_session: AsyncSession,
) -> None:
    # Before compute_freshness existed, every citation's pill was hardcoded
    # to "CURRENT" regardless of how old the underlying accepted_fact
    # actually was - a fail-loud (D-15) violation. A reference-terms fact
    # 60 days old is beyond GILT_REFERENCE_TERMS_FRESHNESS's 30-day SLO but
    # within its 90-day delay tolerance, so it must show DELAYED, not
    # CURRENT.
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(
        db_session, instrument.id,
        knowledge_time=dt.datetime.now(dt.UTC) - dt.timedelta(days=60),
    )
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="tell me about the 2036 gilt",
        principal_id=None, account_id=None,
    )

    dmo_citation = next(c for c in answer.citations if "UK DMO" in c.label)
    assert dmo_citation.pill == "DELAYED"


async def test_gilt_query_about_a_different_gilt_does_not_show_the_wrong_one(
    db_session: AsyncSession,
) -> None:
    # Only the seed gilt is registered in this test's DB, but the query
    # pattern matches ANY "gilt" mention - a query about a maturity year
    # nothing matches must NOT silently show this instrument's facts.
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, instrument.id)
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="tell me about the 2065 gilt",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None, "must never show the 2036 gilt's facts for a 2065 question"
    assert answer.evidence_bundle_id is None
    assert "2065" in answer.text


async def test_gilt_query_resolves_a_different_gilt_by_year(db_session: AsyncSession) -> None:
    # scripts.onboard_all_gilts widened real coverage beyond the single
    # seed instrument - a year matching a DIFFERENT onboarded gilt must
    # actually return THAT gilt's facts, not just correctly refuse.
    await _seed_capability_and_jurisdiction(db_session)
    seed_instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, seed_instrument.id)
    other = await _seed_another_gilt(
        db_session, isin="GB00BYYMZX75", name="2½% Treasury Gilt 2065",
        redemption_date="2065-07-22", coupon_rate="2.5",
    )
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="what is the coupon rate of the 2065 gilt?",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["ISIN"] == "GB00BYYMZX75"
    assert rows["Coupon"] == "2.5% semi-annual"
    assert rows["Maturity"] == "2065-07-22"
    assert other.id != seed_instrument.id  # sanity: genuinely a different instrument


async def test_gilt_query_with_ambiguous_year_asks_which_one(db_session: AsyncSession) -> None:
    # Real UK gilts often share a maturity year (confirmed live: four
    # different gilts mature in 2029) - never guess one, ask.
    await _seed_capability_and_jurisdiction(db_session)
    seed_instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, seed_instrument.id)
    await _seed_another_gilt(
        db_session, isin="GB00BWBR1N39", name="4 7/8% Treasury Gilt 2036",
        redemption_date="2036-07-31", coupon_rate="4.875",
    )
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="coupon rate of the 2036 gilt",
        principal_id=None, account_id=None,
    )

    assert answer.facts is None
    assert answer.evidence_bundle_id is None
    assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION
    assert "4¼% Treasury Stock 2036" in answer.text or "4 1/4% Treasury Stock 2036" in answer.text
    assert "4 7/8% Treasury Gilt 2036" in answer.text
    assert "which one" in answer.text.lower()


async def test_ambiguous_year_follow_up_naming_one_option_resolves_it(
    db_session: AsyncSession,
) -> None:
    # A real bug found via live testing: asking about "2027"/"2036" gets an
    # ambiguous-year list back, and replying with one of the EXACT options
    # just offered (its instrument_name, copied verbatim) must resolve to
    # that gilt, not repeat the same ambiguous list - "2036" is still
    # present in the follow-up, so only the year-based lookup ran before.
    await _seed_capability_and_jurisdiction(db_session)
    seed_instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, seed_instrument.id)
    await _seed_another_gilt(
        db_session, isin="GB00BWBR1N39", name="4 7/8% Treasury Gilt 2036",
        redemption_date="2036-07-31", coupon_rate="4.875",
    )
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="4 7/8% Treasury Gilt 2036",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["ISIN"] == "GB00BWBR1N39"
    assert rows["Coupon"] == "4.875% semi-annual"


async def test_ambiguous_year_follow_up_naming_an_isin_resolves_it(
    db_session: AsyncSession,
) -> None:
    # ISIN alone never carries a year token _mentioned_year can extract
    # (no word boundary inside a contiguous alphanumeric string), so this
    # only exercises the narrowing branch when the year is repeated too -
    # a natural follow-up like "the 2036 one, GB00BWBR1N39".
    await _seed_capability_and_jurisdiction(db_session)
    seed_instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, seed_instrument.id)
    await _seed_another_gilt(
        db_session, isin="GB00BWBR1N39", name="4 7/8% Treasury Gilt 2036",
        redemption_date="2036-07-31", coupon_rate="4.875",
    )
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="the 2036 one, GB00BWBR1N39",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None
    rows = dict(answer.facts.rows)
    assert rows["ISIN"] == "GB00BWBR1N39"


async def test_gilt_query_with_no_year_mentioned_shows_the_one_seeded_gilt(
    db_session: AsyncSession,
) -> None:
    # A generic gilt question (no specific year) is fine to answer with the
    # one gilt that exists - there's no ambiguity to guard against here.
    await _seed_capability_and_jurisdiction(db_session)
    instrument = await _seed_gilt(db_session)
    await _seed_reference_fact(db_session, instrument.id)
    await _seed_rights_profile(db_session, code="uk-dmo.gilts", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="what are the terms of the treasury gilt",
        principal_id=None, account_id=None,
    )

    assert answer.facts is not None


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


async def test_yield_curve_query_pill_reflects_oldest_contributing_point(
    db_session: AsyncSession,
) -> None:
    # UK_GILT_NOMINAL_SPOT_CURVE_FRESHNESS: 1-day SLO, 7-day stale threshold.
    # 10 days old is beyond both, so the curve citation must say STALE, not
    # the old hardcoded "CURRENT".
    await _seed_capability_and_jurisdiction(db_session)
    await _seed_curve_points(
        db_session, _CURVE_FIXTURE,
        knowledge_time=dt.datetime.now(dt.UTC) - dt.timedelta(days=10),
    )
    await _seed_rights_profile(db_session, code="boe.yield-curve", actions=["display"])

    answer = await assemble_research_answer(
        db_session, query_text="what's the current UK yield curve?",
        principal_id=None, account_id=None,
    )

    assert answer.citations[0].pill == "STALE"


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


async def test_help_query_lists_real_current_topics(db_session: AsyncSession) -> None:
    await _seed_capability_and_jurisdiction(db_session)

    answer = await assemble_research_answer(
        db_session, query_text="which topics do u answer",
        principal_id=None, account_id=None,
    )

    assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION
    assert "gilt reference terms" in answer.text.lower()
    assert "spot curve" in answer.text.lower()
    assert "accrued" in answer.text.lower()
    assert answer.facts is None
    assert answer.evidence_bundle_id is None


async def test_bare_greeting_gets_a_short_conversational_reply_not_the_cold_default(
    db_session: AsyncSession,
) -> None:
    """A real bug found via live UI testing: "hi" used to fall all the way
    through to the generic "no data" default, identical to a genuinely
    failed lookup - a poor first impression and not actually "no data",
    just no *query* to look anything up for. A second real complaint after
    that fix: routing "hi" to the full bulleted _CAPABILITY_SUMMARY (with
    its recommendation-disclaimer front-loaded) read as a scripted bot
    reply, not a chat - the greeting reply is now a short, plain sentence
    instead, and the full list stays reserved for an explicit "what can
    you do" (_help_reply, see test_help_query_lists_real_current_topics).
    """
    await _seed_capability_and_jurisdiction(db_session)

    for greeting in ("hi", "Hello!", "hey", "good morning"):
        answer = await assemble_research_answer(
            db_session, query_text=greeting, principal_id=None, account_id=None,
        )
        assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION
        assert not answer.text.startswith('You asked:'), greeting
        assert "-" not in answer.text, f"greeting reply must not be a bulleted list: {greeting}"
        assert len(answer.text) < 220, f"greeting reply must stay short: {greeting}"


async def test_closing_remark_gets_a_warm_reply_not_the_cold_default(
    db_session: AsyncSession,
) -> None:
    """"thank you" used to fall all the way through the document-search
    fallback (no chunk is actually about "thank you") to the same cold,
    generic "no data" default a genuinely failed lookup gets - technically
    correct, but an unfriendly answer to what's obviously a closing remark,
    not a data question.
    """
    await _seed_capability_and_jurisdiction(db_session)

    for closing in ("thanks", "thank you", "Thank you so much!", "cheers", "bye", "ok thanks"):
        answer = await assemble_research_answer(
            db_session, query_text=closing, principal_id=None, account_id=None,
        )
        assert answer.allowed_output_type == AllowedOutputType.NEUTRAL_EDUCATION
        assert "you're welcome" in answer.text.lower(), closing
        assert not answer.text.startswith('You asked:'), closing


async def test_closing_pattern_does_not_false_positive_on_real_questions(
    db_session: AsyncSession,
) -> None:
    """Whole-message match only - "thanks"/"bye" as real words inside an
    actual question must never be mis-routed to the closing branch.
    """
    await _seed_capability_and_jurisdiction(db_session)

    answer = await assemble_research_answer(
        db_session, query_text="thanks to the ex-dividend convention, what is accrued interest",
        principal_id=None, account_id=None,
    )
    assert "you're welcome" not in answer.text.lower()


async def test_greeting_pattern_does_not_false_positive_on_real_questions(
    db_session: AsyncSession,
) -> None:
    """Whole-message match only - "hi" as a real word inside an actual
    question must never be mis-routed to the greeting branch. No gilt
    data seeded here, so _gilt_facts_reply itself falls back to
    NEUTRAL_EDUCATION too - the distinguishing signal is *which* fallback
    text comes back: _gilt_facts_reply's own default("gilt reference
    facts") label, not the greeting/help branch's capability list.
    """
    await _seed_capability_and_jurisdiction(db_session)

    answer = await assemble_research_answer(
        db_session, query_text="hi there, what is the gilt price",
        principal_id=None, account_id=None,
    )
    assert "Right now I can answer" not in answer.text
    assert 'You asked: "gilt reference facts"' in answer.text
