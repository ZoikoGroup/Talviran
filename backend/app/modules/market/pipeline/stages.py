"""Orchestrates one GiltReferenceCandidate (week 8's connector output)
through the pipeline stages this module owns: rights check -> identity
resolve -> observation write -> reconcile/publish. Acquire/manifest/
validate/normalise already happened in the connector (week 8) before a
candidate ever reaches here.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.dmo_gilts.mapping import GiltReferenceCandidate
from app.modules.market.models import SourceObservation
from app.modules.market.pipeline.identity_resolution import (
    ResolvedIdentity,
    resolve_instrument_by_isin,
)
from app.modules.market.pipeline.reconcile import (
    CandidateObservation,
    ReconciliationOutcome,
    reconcile_and_publish,
)
from app.modules.market.pipeline.reconciliation_policy import GILT_REFERENCE_TERMS_POLICY
from app.modules.rights.engine import RightsDecision, evaluate_action

METRIC_GILT_REFERENCE_TERMS = "GILT_REFERENCE_TERMS"


@dataclass(frozen=True)
class IngestSkipped:
    reason: str


@dataclass(frozen=True)
class IngestResult:
    observation_id: uuid.UUID
    reconciliation: ReconciliationOutcome


def candidate_value(candidate: GiltReferenceCandidate) -> dict[str, Any]:
    """The canonical JSON shape stored in source_observation.raw_value and
    accepted_fact.value — also what reconcile_and_publish diffs on to
    decide NO_CHANGE vs a new version.
    """
    return {
        "instrument_name": candidate.instrument_name,
        "gilt_type": candidate.gilt_type,
        "coupon_rate": str(candidate.coupon_rate) if candidate.coupon_rate is not None else None,
        "redemption_date": candidate.redemption_date.isoformat(),
        "first_issue_date": candidate.first_issue_date.isoformat(),
        "dividend_dates": candidate.dividend_dates,
    }


def semantic_observation_key(
    *, source_code: str, dataset_code: str, isin: str, metric_id: str, as_of: str
) -> str:
    raw = f"{source_code}:{dataset_code}:{isin}:{metric_id}:{as_of}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def ingest_gilt_reference_candidate(
    session: AsyncSession,
    *,
    candidate: GiltReferenceCandidate,
    source_artifact_id: uuid.UUID,
    source_code: str,
    dataset_code: str,
    rights_profile_id: uuid.UUID,
    fetched_at: dt.datetime,
) -> IngestResult | IngestSkipped:
    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return IngestSkipped(reason=f"rights check denied 'store' for profile {rights_profile_id}")

    identity = await resolve_instrument_by_isin(session, candidate.isin)
    if not isinstance(identity, ResolvedIdentity):
        return IngestSkipped(reason=identity.reason)

    key = semantic_observation_key(
        source_code=source_code,
        dataset_code=dataset_code,
        isin=candidate.isin,
        metric_id=METRIC_GILT_REFERENCE_TERMS,
        as_of=candidate.close_of_business_date.isoformat(),
    )
    value = candidate_value(candidate)

    existing = (
        await session.execute(
            select(SourceObservation).where(SourceObservation.semantic_observation_key == key)
        )
    ).scalar_one_or_none()

    if existing is not None:
        observation_id = existing.id
    else:
        observation = SourceObservation(
            source_artifact_id=source_artifact_id,
            rights_profile_id=rights_profile_id,
            subject_type="INSTRUMENT",
            subject_id=identity.instrument_id,
            metric_id=METRIC_GILT_REFERENCE_TERMS,
            semantic_observation_key=key,
            raw_value=value,
            valid_from=candidate.first_issue_date,
            observed_at=fetched_at,
        )
        session.add(observation)
        await session.flush()
        observation_id = observation.id

    # Reference terms are valid from issuance onward, indefinitely — not
    # from "when we happened to observe them." A future correction to this
    # same fact reuses this same valid_range; only knowledge_range changes.
    valid_from = dt.datetime.combine(candidate.first_issue_date, dt.time.min, tzinfo=dt.UTC)

    reconciliation = await reconcile_and_publish(
        session,
        subject_type="INSTRUMENT",
        subject_id=identity.instrument_id,
        metric_id=METRIC_GILT_REFERENCE_TERMS,
        candidates=[
            CandidateObservation(
                observation_id=observation_id, source_code=source_code, value=value
            )
        ],
        policy=GILT_REFERENCE_TERMS_POLICY,
        valid_range=Range(lower=valid_from, upper=None, bounds="[)"),
        knowledge_time=fetched_at,
    )

    return IngestResult(observation_id=observation_id, reconciliation=reconciliation)
