"""Orchestrates one TreasurySecurityCandidate through the pipeline stages
this module owns: rights check -> identity resolve -> observation write ->
reconcile/publish. Mirrors market/pipeline/stages.py's gilt-reference-terms
path exactly, including its division of labour — acquire/manifest/
validate/normalise already happened in the connector before a candidate
ever reaches here.

Identity resolution uses CUSIP, not ISIN — resolve_instrument_by_alias is
already generic over alias_type (see identity_resolution.py), so this
needs no new resolver, just a different alias_type.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.treasury_securities.mapping import TreasurySecurityCandidate
from app.modules.market.pipeline.identity_resolution import (
    ResolvedIdentity,
    resolve_instrument_by_alias,
)
from app.modules.market.pipeline.ingest_tail import ingest_and_reconcile
from app.modules.market.pipeline.reconcile import ReconciliationOutcome
from app.modules.market.pipeline.reconciliation_policy import (
    TREASURY_SECURITY_REFERENCE_TERMS_POLICY,
)
from app.modules.rights.engine import RightsDecision, evaluate_action

METRIC_TREASURY_SECURITY_REFERENCE_TERMS = "TREASURY_SECURITY_REFERENCE_TERMS"


@dataclass(frozen=True)
class TreasurySecurityIngestSkipped:
    reason: str


@dataclass(frozen=True)
class TreasurySecurityIngestResult:
    observation_id: uuid.UUID
    reconciliation: ReconciliationOutcome


def treasury_security_candidate_value(candidate: TreasurySecurityCandidate) -> dict[str, Any]:
    return {
        "security_type": candidate.security_type,
        "security_term": candidate.security_term,
        "coupon_rate": str(candidate.coupon_rate),
        "maturity_date": candidate.maturity_date.isoformat(),
        "issue_date": candidate.issue_date.isoformat(),
    }


def treasury_security_semantic_observation_key(
    *, source_code: str, dataset_code: str, cusip: str, issue_date: dt.date
) -> str:
    raw = f"{source_code}:{dataset_code}:{cusip}:{issue_date.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def ingest_treasury_security_reference_candidate(
    session: AsyncSession,
    *,
    candidate: TreasurySecurityCandidate,
    source_artifact_id: uuid.UUID,
    source_code: str,
    dataset_code: str,
    rights_profile_id: uuid.UUID,
    fetched_at: dt.datetime,
) -> TreasurySecurityIngestResult | TreasurySecurityIngestSkipped:
    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return TreasurySecurityIngestSkipped(
            reason=f"rights check denied 'store' for profile {rights_profile_id}"
        )

    identity = await resolve_instrument_by_alias(
        session, alias_type="CUSIP", alias_value=candidate.cusip
    )
    if not isinstance(identity, ResolvedIdentity):
        return TreasurySecurityIngestSkipped(reason=identity.reason)

    key = treasury_security_semantic_observation_key(
        source_code=source_code,
        dataset_code=dataset_code,
        cusip=candidate.cusip,
        issue_date=candidate.issue_date,
    )
    value = treasury_security_candidate_value(candidate)

    # Reference terms are valid from issuance onward, indefinitely - not
    # from "when we happened to observe them." Mirrors stages.py's own
    # gilt-reference-terms reasoning exactly.
    valid_from_dt = dt.datetime.combine(candidate.issue_date, dt.time.min, tzinfo=dt.UTC)

    outcome = await ingest_and_reconcile(
        session,
        source_artifact_id=source_artifact_id,
        source_code=source_code,
        rights_profile_id=rights_profile_id,
        subject_type="INSTRUMENT",
        subject_id=identity.instrument_id,
        metric_id=METRIC_TREASURY_SECURITY_REFERENCE_TERMS,
        semantic_observation_key=key,
        value=value,
        valid_from=candidate.issue_date,
        valid_range=Range(lower=valid_from_dt, upper=None, bounds="[)"),
        fetched_at=fetched_at,
        policy=TREASURY_SECURITY_REFERENCE_TERMS_POLICY,
    )

    return TreasurySecurityIngestResult(
        observation_id=outcome.observation_id, reconciliation=outcome.reconciliation
    )
