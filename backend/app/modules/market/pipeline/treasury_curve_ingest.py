"""Orchestrates one CurvePointCandidate (US Treasury connector output)
through the pipeline stages this module owns: rights check -> observation
write -> reconcile/publish. Mirrors market/pipeline/curve_ingest.py's own
UK gilt curve exactly, including its reasoning for skipping identity
resolution: a Treasury tenor field name like "BC_10YEAR" carries no
ambiguity to resolve — it's an exact field name from the source, not free
text matched against a catalogue — so subject_id is a fixed, deterministic
UUID5 derived from the field name itself.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.treasury_yield_curve.mapping import CurvePointCandidate
from app.modules.market.pipeline.ingest_tail import ingest_and_reconcile
from app.modules.market.pipeline.reconcile import ReconciliationOutcome
from app.modules.market.pipeline.reconciliation_policy import (
    US_TREASURY_PAR_YIELD_CURVE_POLICY,
)
from app.modules.rights.engine import RightsDecision, evaluate_action

METRIC_US_TREASURY_PAR_YIELD_CURVE = "US_TREASURY_PAR_YIELD_CURVE"
SUBJECT_TYPE_TREASURY_CURVE_POINT = "TREASURY_CURVE_POINT"

# Fixed, never regenerate: changing this would silently orphan every
# previously-published curve-point fact under a new, unrelated subject_id.
_CURVE_POINT_NAMESPACE = uuid.UUID("8ca4e12d-0901-4f4c-92d0-5e04d948ec84")


def treasury_curve_point_subject_id(tenor_field: str) -> uuid.UUID:
    return uuid.uuid5(_CURVE_POINT_NAMESPACE, f"US-TREASURY-PAR-{tenor_field}")


@dataclass(frozen=True)
class TreasuryCurveIngestSkipped:
    reason: str


@dataclass(frozen=True)
class TreasuryCurveIngestResult:
    observation_id: uuid.UUID
    reconciliation: ReconciliationOutcome


def treasury_curve_point_value(candidate: CurvePointCandidate) -> dict[str, str]:
    # tenor_field/tenor_label are redundant with subject_id (a one-way uuid5
    # hash of tenor_field) but a fact must be self-describing to a reader -
    # nothing should have to reverse-engineer a hash to know what it means.
    return {
        "tenor_field": candidate.tenor_field,
        "tenor_label": candidate.tenor_label,
        "par_yield_pct": str(candidate.par_yield_pct),
    }


def treasury_curve_semantic_observation_key(
    *, source_code: str, dataset_code: str, tenor_field: str, curve_date: dt.date
) -> str:
    raw = f"{source_code}:{dataset_code}:{tenor_field}:{curve_date.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def ingest_treasury_curve_point_candidate(
    session: AsyncSession,
    *,
    candidate: CurvePointCandidate,
    source_artifact_id: uuid.UUID,
    source_code: str,
    dataset_code: str,
    rights_profile_id: uuid.UUID,
    fetched_at: dt.datetime,
) -> TreasuryCurveIngestResult | TreasuryCurveIngestSkipped:
    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return TreasuryCurveIngestSkipped(
            reason=f"rights check denied 'store' for profile {rights_profile_id}"
        )

    subject_id = treasury_curve_point_subject_id(candidate.tenor_field)
    key = treasury_curve_semantic_observation_key(
        source_code=source_code,
        dataset_code=dataset_code,
        tenor_field=candidate.tenor_field,
        curve_date=candidate.curve_date,
    )
    value = treasury_curve_point_value(candidate)

    # A curve point is valid for exactly its own calendar day - unlike gilt
    # reference terms, which are valid indefinitely from issuance. Today's
    # yield does not "correct" yesterday's; it's a different real-world fact.
    day_start = dt.datetime.combine(candidate.curve_date, dt.time.min, tzinfo=dt.UTC)
    valid_range: Range[dt.datetime] = Range(
        lower=day_start, upper=day_start + dt.timedelta(days=1), bounds="[)"
    )

    outcome = await ingest_and_reconcile(
        session,
        source_artifact_id=source_artifact_id,
        source_code=source_code,
        rights_profile_id=rights_profile_id,
        subject_type=SUBJECT_TYPE_TREASURY_CURVE_POINT,
        subject_id=subject_id,
        metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
        semantic_observation_key=key,
        value=value,
        valid_from=candidate.curve_date,
        valid_range=valid_range,
        fetched_at=fetched_at,
        policy=US_TREASURY_PAR_YIELD_CURVE_POLICY,
    )

    return TreasuryCurveIngestResult(
        observation_id=outcome.observation_id, reconciliation=outcome.reconciliation
    )
