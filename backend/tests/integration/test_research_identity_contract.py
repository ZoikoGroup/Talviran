"""G02/G04 acceptance suite (REG-01 identity, REG-02 capability) - start of
the 60-labeled-case suite the UAT gap analysis calls for. Each test below is
one labeled fixture from that spec's own worked examples (NVIDIA/NVDA,
Alphabet/GOOGL/GOOG, MercadoLibre/MELI) or a directly-named failure mode
(typo, share-class collapse, unregistered metric). Extend this file with
further labeled cases rather than starting a second suite.
"""

import datetime as dt
import uuid

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.models import AcceptedFact
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer
from app.modules.research.identity_contract import (
    AmbiguousEntity,
    CapabilityState,
    ResolvedEntity,
    UnresolvedEntity,
    decide_capability,
    resolve_research_entity,
)


async def _make_instrument(
    db_session: AsyncSession,
    *,
    issuer_name: str,
    instrument_name: str,
    ticker: str,
    isin: str | None = None,
) -> Instrument:
    issuer = Issuer(name=issuer_name, country_code="US")
    db_session.add(issuer)
    await db_session.flush()

    instrument = Instrument(
        issuer_id=issuer.id,
        instrument_type="EQUITY",
        name=instrument_name,
        currency_code="USD",
    )
    db_session.add(instrument)
    await db_session.flush()

    db_session.add(
        InstrumentAlias(
            instrument_id=instrument.id, alias_type="TICKER", alias_value=ticker.upper()
        )
    )
    if isin:
        db_session.add(
            InstrumentAlias(instrument_id=instrument.id, alias_type="ISIN", alias_value=isin)
        )
    await db_session.commit()
    return instrument


# ---------------------------------------------------------------- REG-01 identity


async def test_exact_ticker_resolves_to_one_instrument(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    inst = await _make_instrument(
        db_session, issuer_name=f"NVIDIA Corp {suffix}", instrument_name="NVIDIA Corporation",
        ticker=f"NVDA{suffix}",
    )
    result = await resolve_research_entity(db_session, f"NVDA{suffix}")
    assert isinstance(result, ResolvedEntity)
    assert result.candidate.instrument_id == inst.id


async def test_cashtag_with_dollar_sign_normalizes_and_resolves(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    inst = await _make_instrument(
        db_session, issuer_name=f"MercadoLibre {suffix}", instrument_name="MercadoLibre Inc",
        ticker=f"MELI{suffix}",
    )
    result = await resolve_research_entity(db_session, f"${f'MELI{suffix}'}")
    assert isinstance(result, ResolvedEntity)
    assert result.candidate.instrument_id == inst.id


async def test_isin_resolves_exactly(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    isin = f"US{suffix.upper()}01"
    inst = await _make_instrument(
        db_session, issuer_name=f"Issuer {suffix}", instrument_name="Some Instrument",
        ticker=f"TICK{suffix}", isin=isin,
    )
    result = await resolve_research_entity(db_session, isin)
    assert isinstance(result, ResolvedEntity)
    assert result.candidate.instrument_id == inst.id


async def test_lowercase_and_whitespace_normalize_before_matching(
    db_session: AsyncSession,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    inst = await _make_instrument(
        db_session, issuer_name=f"Lower Co {suffix}", instrument_name="Lower Co",
        ticker=f"LOW{suffix}",
    )
    result = await resolve_research_entity(db_session, f"  low{suffix.lower()}  ")
    assert isinstance(result, ResolvedEntity)
    assert result.candidate.instrument_id == inst.id


async def test_share_class_variants_are_distinct_not_collapsed(db_session: AsyncSession) -> None:
    """GOOGL and GOOG must resolve to two DIFFERENT instrument_ids, not be
    merged into one "Alphabet" row - the exact defect G02 names."""
    suffix = uuid.uuid4().hex[:8]
    issuer = Issuer(name=f"Alphabet {suffix}", country_code="US")
    db_session.add(issuer)
    await db_session.flush()

    class_a = Instrument(
        issuer_id=issuer.id, instrument_type="EQUITY", name="Alphabet Class A", currency_code="USD"
    )
    class_c = Instrument(
        issuer_id=issuer.id, instrument_type="EQUITY", name="Alphabet Class C", currency_code="USD"
    )
    db_session.add_all([class_a, class_c])
    await db_session.flush()
    db_session.add_all(
        [
            InstrumentAlias(
                instrument_id=class_a.id, alias_type="TICKER", alias_value=f"GOOGL{suffix}".upper()
            ),
            InstrumentAlias(
                instrument_id=class_c.id, alias_type="TICKER", alias_value=f"GOOG{suffix}".upper()
            ),
        ]
    )
    await db_session.commit()

    result_a = await resolve_research_entity(db_session, f"GOOGL{suffix}")
    result_c = await resolve_research_entity(db_session, f"GOOG{suffix}")
    assert isinstance(result_a, ResolvedEntity) and isinstance(result_c, ResolvedEntity)
    assert result_a.candidate.instrument_id == class_a.id
    assert result_c.candidate.instrument_id == class_c.id
    assert result_a.candidate.instrument_id != result_c.candidate.instrument_id


async def test_issuer_name_spanning_two_share_classes_is_ambiguous(
    db_session: AsyncSession,
) -> None:
    """Asking for the issuer by name alone, with more than one listing on
    file, must clarify rather than silently pick one."""
    suffix = uuid.uuid4().hex[:8]
    issuer_name = f"Ambiguous Issuer {suffix}"
    issuer = Issuer(name=issuer_name, country_code="US")
    db_session.add(issuer)
    await db_session.flush()
    inst_1 = Instrument(
        issuer_id=issuer.id, instrument_type="EQUITY", name="Listing One", currency_code="USD"
    )
    inst_2 = Instrument(
        issuer_id=issuer.id, instrument_type="EQUITY", name="Listing Two", currency_code="USD"
    )
    db_session.add_all([inst_1, inst_2])
    await db_session.commit()

    result = await resolve_research_entity(db_session, issuer_name)
    assert isinstance(result, AmbiguousEntity)
    assert {c.instrument_id for c in result.candidates} == {inst_1.id, inst_2.id}


async def test_unknown_symbol_is_unresolved_not_guessed(db_session: AsyncSession) -> None:
    """A typo/unknown ticker must come back UNRESOLVED, never fuzzy-matched
    to the nearest real instrument."""
    suffix = uuid.uuid4().hex[:8]
    await _make_instrument(
        db_session, issuer_name=f"Real Co {suffix}", instrument_name="Real Co",
        ticker=f"REAL{suffix}",
    )
    result = await resolve_research_entity(db_session, f"REALX{suffix}")
    assert isinstance(result, UnresolvedEntity)


async def test_empty_request_is_unresolved(db_session: AsyncSession) -> None:
    result = await resolve_research_entity(db_session, "   ")
    assert isinstance(result, UnresolvedEntity)
    assert result.reason == "empty request"


# ------------------------------------------------------------- REG-02 capability


async def test_capability_available_for_fresh_accepted_fact(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    inst = await _make_instrument(
        db_session, issuer_name=f"Fresh Co {suffix}", instrument_name="Fresh Co",
        ticker=f"FRESH{suffix}",
    )
    now = dt.datetime.now(dt.UTC)
    db_session.add(
        AcceptedFact(
            subject_type="INSTRUMENT",
            subject_id=inst.id,
            metric_id="EQUITY_EOD_PRICE",
            valid_range=Range(now - dt.timedelta(hours=1), None),
            knowledge_range=Range(now - dt.timedelta(hours=1), None),
            value={"price": "123.45"},
            status="ACTIVE",
        )
    )
    await db_session.commit()

    decision = await decide_capability(
        db_session, instrument_id=inst.id, metric_id="EQUITY_EOD_PRICE"
    )
    assert decision.state == CapabilityState.AVAILABLE


async def test_capability_stale_for_old_accepted_fact(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    inst = await _make_instrument(
        db_session, issuer_name=f"Stale Co {suffix}", instrument_name="Stale Co",
        ticker=f"STALE{suffix}",
    )
    old = dt.datetime.now(dt.UTC) - dt.timedelta(days=10)
    db_session.add(
        AcceptedFact(
            subject_type="INSTRUMENT",
            subject_id=inst.id,
            metric_id="EQUITY_EOD_PRICE",
            valid_range=Range(old, None),
            knowledge_range=Range(old, None),
            value={"price": "99.00"},
            status="ACTIVE",
        )
    )
    await db_session.commit()

    decision = await decide_capability(
        db_session, instrument_id=inst.id, metric_id="EQUITY_EOD_PRICE"
    )
    assert decision.state == CapabilityState.STALE


async def test_capability_unsupported_for_unregistered_metric(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    inst = await _make_instrument(
        db_session, issuer_name=f"NoMetric Co {suffix}", instrument_name="NoMetric Co",
        ticker=f"NOMET{suffix}",
    )
    decision = await decide_capability(
        db_session, instrument_id=inst.id, metric_id="NOT_A_REGISTERED_METRIC"
    )
    assert decision.state == CapabilityState.UNSUPPORTED
    assert "no freshness profile" in decision.reason


async def test_capability_unsupported_when_no_accepted_fact_exists(
    db_session: AsyncSession,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    inst = await _make_instrument(
        db_session, issuer_name=f"NoData Co {suffix}", instrument_name="NoData Co",
        ticker=f"NODATA{suffix}",
    )
    decision = await decide_capability(
        db_session, instrument_id=inst.id, metric_id="EQUITY_EOD_PRICE"
    )
    assert decision.state == CapabilityState.UNSUPPORTED
    assert "no accepted fact" in decision.reason
