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

from app.modules.market.models import SourceObservation
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

    reconciliation = await reconcile_and_publish(
        session,
        subject_type=subject_type,
        subject_id=subject_id,
        metric_id=metric_id,
        candidates=[
            CandidateObservation(
                observation_id=observation_id, source_code=source_code, value=value
            )
        ],
        policy=policy,
        valid_range=valid_range,
        knowledge_time=fetched_at,
    )

    return IngestOutcome(observation_id=observation_id, reconciliation=reconciliation)
