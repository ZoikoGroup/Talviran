"""End-to-end: real DBnomics fixture -> connector.parse() -> macro ingest
-> a real accepted_fact row. Proves the DBnomics connector and the shared
ingest_and_reconcile tail actually work together, not just each in
isolation.
"""

import datetime as dt
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.base import AcquiredPayload
from app.modules.market.connectors.dbnomics_macro.mapping import MacroObservationCandidate
from app.modules.market.connectors.dbnomics_macro.reference_connector import (
    DBnomicsMacroConnector,
)
from app.modules.market.models import AcceptedFact, Dataset, Source, SourceArtifact
from app.modules.market.pipeline.macro_ingest import (
    MacroIngestSkipped,
    ingest_macro_observation_candidate,
    macro_series_subject_id,
)
from app.modules.market.pipeline.reconciliation_policy import MACRO_GDP_POLICY
from app.modules.rights.models import RightsGrant, RightsProfile

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "dbnomics_india_gdp.json"


async def _seed_rights_profile(session: AsyncSession) -> uuid.UUID:
    profile = RightsProfile(code=f"dbnomics.macro.test.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(
        RightsGrant(rights_profile_id=profile.id, action="store", permission_state="ALLOW")
    )
    await session.flush()
    return profile.id


async def _seed_source_artifact(session: AsyncSession) -> SourceArtifact:
    source = Source(code=f"dbnomics-test-{uuid.uuid4().hex[:8]}", name="DBnomics (test)")
    session.add(source)
    await session.flush()
    dataset = Dataset(source_id=source.id, code="wdi-gdp", name="WDI GDP")
    session.add(dataset)
    await session.flush()
    artifact = SourceArtifact(
        dataset_id=dataset.id,
        sha256="4" * 64,
        storage_ref="test://dbnomics-fixture",
        media_type="application/json",
        byte_length=len(FIXTURE_PATH.read_bytes()),
        retrieved_at=dt.datetime.now(dt.UTC),
    )
    session.add(artifact)
    await session.flush()
    return artifact


def _parse_fixture() -> list[MacroObservationCandidate]:
    connector = DBnomicsMacroConnector(
        httpx.AsyncClient(), provider_code="WB", dataset_code="WDI",
        series_code="A-NY.GDP.MKTP.CD-IND",
    )
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="application/json",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="test",
    )
    candidates = connector.parse(payload)
    return [c for c in candidates if isinstance(c, MacroObservationCandidate)]


def _latest(candidates: list[MacroObservationCandidate]) -> MacroObservationCandidate:
    # A real response carries the series' full history (DBnomics'
    # `observations=1` is a boolean "include observations" flag, not a
    # limit) — picking "the latest" is the caller's job, same as
    # ingest_dev_data.py filters the BoE curve feed to its latest date.
    return max(candidates, key=lambda c: c.period_start_day)


async def test_real_fixture_flows_through_to_an_accepted_fact(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)
    fetched_at = dt.datetime.now(dt.UTC)

    candidate = _latest(_parse_fixture())

    result = await ingest_macro_observation_candidate(
        db_session,
        candidate=candidate,
        metric_id="MACRO_GDP",
        policy=MACRO_GDP_POLICY,
        source_artifact_id=artifact.id,
        source_code="dbnomics",
        dataset_code="wdi-gdp",
        rights_profile_id=rights_profile_id,
        fetched_at=fetched_at,
    )
    await db_session.commit()

    assert not isinstance(result, MacroIngestSkipped)
    assert result.reconciliation.decision == "ACCEPTED"

    fact = await db_session.get(AcceptedFact, result.reconciliation.accepted_fact_id)
    assert fact is not None
    assert fact.status == "ACTIVE"
    assert fact.subject_type == "MACRO_SERIES"
    assert fact.subject_id == macro_series_subject_id("WB", "WDI", "A-NY.GDP.MKTP.CD-IND")
    assert fact.value == {
        "provider_code": "WB",
        "dataset_code": "WDI",
        "series_code": "A-NY.GDP.MKTP.CD-IND",
        "period": "2023",
        "value": "3549918918777.53",
    }


async def test_reingesting_the_same_period_is_no_change(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)
    candidate = _latest(_parse_fixture())

    first = await ingest_macro_observation_candidate(
        db_session, candidate=candidate, metric_id="MACRO_GDP", policy=MACRO_GDP_POLICY,
        source_artifact_id=artifact.id, source_code="dbnomics", dataset_code="wdi-gdp",
        rights_profile_id=rights_profile_id, fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    second = await ingest_macro_observation_candidate(
        db_session, candidate=candidate, metric_id="MACRO_GDP", policy=MACRO_GDP_POLICY,
        source_artifact_id=artifact.id, source_code="dbnomics", dataset_code="wdi-gdp",
        rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
    )
    await db_session.commit()

    assert not isinstance(first, MacroIngestSkipped) and not isinstance(second, MacroIngestSkipped)
    assert first.observation_id == second.observation_id
    assert second.reconciliation.decision == "NO_CHANGE"


async def test_a_revised_value_for_the_same_period_supersedes(db_session: AsyncSession) -> None:
    rights_profile_id = await _seed_rights_profile(db_session)
    artifact = await _seed_source_artifact(db_session)
    original = _latest(_parse_fixture())
    revised = MacroObservationCandidate(
        provider_code=original.provider_code,
        dataset_code=original.dataset_code,
        series_code=original.series_code,
        period=original.period,
        period_start_day=original.period_start_day,
        period_end_day=original.period_end_day,
        value=original.value + 1,
    )

    first = await ingest_macro_observation_candidate(
        db_session, candidate=original, metric_id="MACRO_GDP", policy=MACRO_GDP_POLICY,
        source_artifact_id=artifact.id, source_code="dbnomics", dataset_code="wdi-gdp",
        rights_profile_id=rights_profile_id, fetched_at=dt.datetime.now(dt.UTC),
    )
    await db_session.commit()

    # A revision reuses the SAME semantic key (same source/dataset/series/
    # period) as the original observation, so it must be a distinct
    # SourceObservation representing a genuinely new raw value — appending
    # a marker to the key the way this test does stands in for "DBnomics
    # re-served this series after a data revision".
    second = await ingest_macro_observation_candidate(
        db_session, candidate=revised, metric_id="MACRO_GDP", policy=MACRO_GDP_POLICY,
        source_artifact_id=artifact.id, source_code="dbnomics-revision",
        dataset_code="wdi-gdp", rights_profile_id=rights_profile_id,
        fetched_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
    )
    await db_session.commit()

    assert not isinstance(first, MacroIngestSkipped) and not isinstance(second, MacroIngestSkipped)
    assert second.reconciliation.decision == "ACCEPTED"

    subject_id = macro_series_subject_id(
        original.provider_code, original.dataset_code, original.series_code
    )
    facts = (
        await db_session.execute(select(AcceptedFact).where(AcceptedFact.subject_id == subject_id))
    ).scalars().all()
    statuses = {f.status for f in facts}
    assert "SUPERSEDED" in statuses and "ACTIVE" in statuses


async def test_denied_rights_skips_ingest(db_session: AsyncSession) -> None:
    profile = RightsProfile(code=f"dbnomics.norights.{uuid.uuid4().hex[:8]}", status="ACTIVE")
    db_session.add(profile)
    await db_session.flush()
    artifact = await _seed_source_artifact(db_session)
    candidate = _latest(_parse_fixture())

    result = await ingest_macro_observation_candidate(
        db_session, candidate=candidate, metric_id="MACRO_GDP", policy=MACRO_GDP_POLICY,
        source_artifact_id=artifact.id, source_code="dbnomics", dataset_code="wdi-gdp",
        rights_profile_id=profile.id, fetched_at=dt.datetime.now(dt.UTC),
    )

    assert isinstance(result, MacroIngestSkipped)
    assert "rights check denied" in result.reason
