"""Shared tail of every metric-specific ingest function: get-or-create the
SourceObservation row, then reconcile and publish.

Everything before this point (the rights check, and identity resolution or
its equivalent deterministic subject_id derivation) differs per metric and
stays in that metric's own ingest_*_candidate function — only the part that
was already byte-for-byte identical between stages.py and curve_ingest.py
lives here, so a third, fourth, fifth metric doesn't copy-paste it again.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.models import Dataset, Source, SourceArtifact, SourceObservation
from app.modules.market.pipeline.reconcile import (
    CandidateObservation,
    ReconciliationOutcome,
    reconcile_and_publish,
)
from app.modules.market.pipeline.reconciliation_policy import ReconciliationPolicy


@dataclass(frozen=True)
class IngestOutcome:
    observation_id: uuid.UUID
    reconciliation: ReconciliationOutcome


async def _gather_candidates(
    session: AsyncSession,
    *,
    subject_id: uuid.UUID,
    metric_id: str,
    valid_from: dt.date | None,
    this_observation_id: uuid.UUID,
    this_source_code: str,
    this_value: dict[str, Any],
) -> list[CandidateObservation]:
    """Every source's observation for the same real-world subject/metric/day
    - not just the one just ingested. Found via a real gap: every caller
    used to hand reconcile_and_publish a single-element candidate list, so
    its cross-source grouping/CONFLICT/tolerance logic (fully built and
    unit-tested) was structurally unreachable from real ingestion - a
    second source's slightly different value silently "superseded" the
    first's as an ordinary value change, never compared against it at all.

    valid_from=None skips gathering and returns just this observation,
    matching every caller's behavior before this existed - no real caller
    passes None today (every metric sets it to a real date), but there's
    no reliable "same real-world period" signal to gather siblings by if
    one ever does.
    """
    this_candidate = CandidateObservation(
        observation_id=this_observation_id, source_code=this_source_code, value=this_value
    )
    if valid_from is None:
        return [this_candidate]

    rows = (
        await session.execute(
            select(SourceObservation.id, SourceObservation.raw_value, Source.code)
            .join(SourceArtifact, SourceObservation.source_artifact_id == SourceArtifact.id)
            .join(Dataset, SourceArtifact.dataset_id == Dataset.id)
            .join(Source, Dataset.source_id == Source.id)
            .where(
                SourceObservation.subject_id == subject_id,
                SourceObservation.metric_id == metric_id,
                SourceObservation.valid_from == valid_from,
            )
        )
    ).all()

    candidates = [
        CandidateObservation(observation_id=obs_id, source_code=code, value=raw_value)
        for obs_id, raw_value, code in rows
    ]
    if not any(c.observation_id == this_observation_id for c in candidates):
        # Defensive only - this observation was just flushed in this same
        # transaction, so the query above should always see it too.
        candidates.append(this_candidate)
    return candidates


async def ingest_and_reconcile(
    session: AsyncSession,
    *,
    source_artifact_id: uuid.UUID,
    source_code: str,
    rights_profile_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    metric_id: str,
    semantic_observation_key: str,
    value: dict[str, Any],
    valid_from: dt.date | None,
    valid_range: Range[dt.datetime],
    fetched_at: dt.datetime,
    policy: ReconciliationPolicy,
) -> IngestOutcome:
    existing = (
        await session.execute(
            select(SourceObservation).where(
                SourceObservation.semantic_observation_key == semantic_observation_key
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        observation_id = existing.id
    else:
        observation = SourceObservation(
            source_artifact_id=source_artifact_id,
            rights_profile_id=rights_profile_id,
            subject_type=subject_type,
            subject_id=subject_id,
            metric_id=metric_id,
            semantic_observation_key=semantic_observation_key,
            raw_value=value,
            valid_from=valid_from,
            observed_at=fetched_at,
        )
        session.add(observation)
        await session.flush()
        observation_id = observation.id

    candidates = await _gather_candidates(
        session,
        subject_id=subject_id,
        metric_id=metric_id,
        valid_from=valid_from,
        this_observation_id=observation_id,
        this_source_code=source_code,
        this_value=value,
    )

    reconciliation = await reconcile_and_publish(
        session,
        subject_type=subject_type,
        subject_id=subject_id,
        metric_id=metric_id,
        candidates=candidates,
        policy=policy,
        valid_range=valid_range,
        knowledge_time=fetched_at,
    )

    return IngestOutcome(observation_id=observation_id, reconciliation=reconciliation)
