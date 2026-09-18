"""Orchestrates one CurvePointCandidate (BoE connector output) through the
pipeline stages this module owns: rights check -> observation write ->
reconcile/publish. Acquire/manifest/validate/normalise already happened in
the connector before a candidate ever reaches here — same division of
labour as stages.py's gilt-reference-terms path.

Identity resolution is deliberately skipped here, unlike the ISIN-based
gilt path: DATA-002's "deterministic identity, never fuzzy" rule exists to
stop an AMBIGUOUS external identifier being silently guessed against a
registry. A curve tenor (e.g. "10.0 years") carries no such ambiguity — it
comes directly from the source's own column header, not from matching
free-text against a catalogue — so subject_id is a fixed, deterministic
UUID5 derived from the tenor itself, computed here rather than requiring a
reference-schema row to be pre-seeded for each of the 80 published tenors.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.boe_yield_curve.mapping import CurvePointCandidate
from app.modules.market.pipeline.ingest_tail import ingest_and_reconcile
from app.modules.market.pipeline.reconcile import ReconciliationOutcome
from app.modules.market.pipeline.reconciliation_policy import (
    UK_GILT_NOMINAL_SPOT_CURVE_POLICY,
)
from app.modules.rights.engine import RightsDecision, evaluate_action

METRIC_UK_GILT_NOMINAL_SPOT_CURVE = "UK_GILT_NOMINAL_SPOT_CURVE"
SUBJECT_TYPE_YIELD_CURVE_POINT = "YIELD_CURVE_POINT"

# Fixed, never regenerate: changing this would silently orphan every
# previously-published curve-point fact under a new, unrelated subject_id.
_CURVE_POINT_NAMESPACE = uuid.UUID("cdb1354c-dcd6-4d01-8488-b1f94ffc0cc0")


def curve_point_subject_id(tenor_years: Decimal) -> uuid.UUID:
    return uuid.uuid5(_CURVE_POINT_NAMESPACE, f"UK-GLC-NOMINAL-{tenor_years.normalize()}")


@dataclass(frozen=True)
class CurveIngestSkipped:
    reason: str


@dataclass(frozen=True)
class CurveIngestResult:
    observation_id: uuid.UUID
    reconciliation: ReconciliationOutcome


def curve_point_value(candidate: CurvePointCandidate) -> dict[str, str]:
    # tenor_years is redundant with subject_id (which is a one-way uuid5
    # hash of it) but a fact must be self-describing to a reader — nothing
    # should have to reverse-engineer a hash to know what a fact even means.
    return {
        "tenor_years": str(candidate.tenor_years),
        "spot_rate_pct": str(candidate.spot_rate_pct),
    }


def curve_semantic_observation_key(
    *, source_code: str, dataset_code: str, tenor_years: Decimal, curve_date: dt.date
) -> str:
    raw = f"{source_code}:{dataset_code}:{tenor_years.normalize()}:{curve_date.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def ingest_curve_point_candidate(
    session: AsyncSession,
    *,
    candidate: CurvePointCandidate,
    source_artifact_id: uuid.UUID,
    source_code: str,
    dataset_code: str,
    rights_profile_id: uuid.UUID,
    fetched_at: dt.datetime,
) -> CurveIngestResult | CurveIngestSkipped:
    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return CurveIngestSkipped(
            reason=f"rights check denied 'store' for profile {rights_profile_id}"
        )

    subject_id = curve_point_subject_id(candidate.tenor_years)
    key = curve_semantic_observation_key(
        source_code=source_code,
        dataset_code=dataset_code,
        tenor_years=candidate.tenor_years,
        curve_date=candidate.curve_date,
    )
    value = curve_point_value(candidate)

    # A curve point is valid for exactly its own calendar day — unlike gilt
    # reference terms, which are valid indefinitely from issuance. Today's
    # rate does not "correct" yesterday's; it's a different real-world fact.
    day_start = dt.datetime.combine(candidate.curve_date, dt.time.min, tzinfo=dt.UTC)
    valid_range: Range[dt.datetime] = Range(
        lower=day_start, upper=day_start + dt.timedelta(days=1), bounds="[)"
    )

    outcome = await ingest_and_reconcile(
        session,
        source_artifact_id=source_artifact_id,
        source_code=source_code,
        rights_profile_id=rights_profile_id,
        subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
        subject_id=subject_id,
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        semantic_observation_key=key,
        value=value,
        valid_from=candidate.curve_date,
        valid_range=valid_range,
        fetched_at=fetched_at,
        policy=UK_GILT_NOMINAL_SPOT_CURVE_POLICY,
    )

    return CurveIngestResult(
        observation_id=outcome.observation_id, reconciliation=outcome.reconciliation
    )
