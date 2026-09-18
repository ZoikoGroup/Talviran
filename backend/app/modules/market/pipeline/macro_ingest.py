"""Orchestrates one MacroObservationCandidate (DBnomics connector output)
through the pipeline stages this module owns: rights check -> observation
write -> reconcile/publish. Acquire/manifest/validate/normalise already
happened in the connector before a candidate ever reaches here — same
division of labour as fx_ingest.py's currency-pair path.

Identity resolution is deliberately skipped here, for the same reason it's
skipped for a curve point or an FX pair: a macro series (e.g. India GDP,
provider WB, series A-NY.GDP.MKTP.CD-IND) carries no identity ambiguity to
resolve — it comes directly from DBnomics' own provider/dataset/series
codes, not from matching free text against a catalogue — so subject_id is
a fixed, deterministic UUID5 derived from those codes. A macro series is
also not naturally an "instrument with an issuer" (no issuer, no trading
currency in the reference.instrument sense), so it deliberately never
touches reference.instrument at all.

metric_id and policy are supplied by the caller, not hardcoded here: one
ingest function serves every DBnomics series regardless of what it
measures (GDP, CPI, ...) — the pilot series configuration decides which
metric_id (and therefore which FreshnessProfile) and which
ReconciliationPolicy a given series maps to.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.dbnomics_macro.mapping import MacroObservationCandidate
from app.modules.market.pipeline.ingest_tail import IngestOutcome, ingest_and_reconcile
from app.modules.market.pipeline.reconciliation_policy import ReconciliationPolicy
from app.modules.rights.engine import RightsDecision, evaluate_action

SUBJECT_TYPE_MACRO_SERIES = "MACRO_SERIES"

# Fixed, never regenerate: changing this would silently orphan every
# previously-published macro fact under a new, unrelated subject_id.
_MACRO_SERIES_NAMESPACE = uuid.UUID("68947249-8b37-45cf-b460-89e18280e14d")


def macro_series_subject_id(provider_code: str, dataset_code: str, series_code: str) -> uuid.UUID:
    return uuid.uuid5(
        _MACRO_SERIES_NAMESPACE, f"MACRO:{provider_code}:{dataset_code}:{series_code}"
    )


@dataclass(frozen=True)
class MacroIngestSkipped:
    reason: str


def macro_observation_value(candidate: MacroObservationCandidate) -> dict[str, str]:
    # provider/dataset/series/period are redundant with subject_id (a
    # one-way uuid5 hash of the first three) but a fact must be
    # self-describing to a reader — nothing should have to
    # reverse-engineer a hash to know what a fact even means.
    return {
        "provider_code": candidate.provider_code,
        "dataset_code": candidate.dataset_code,
        "series_code": candidate.series_code,
        "period": candidate.period,
        "value": str(candidate.value),
    }


def macro_semantic_observation_key(
    *, source_code: str, dataset_code: str, series_code: str, period: str
) -> str:
    raw = f"{source_code}:{dataset_code}:{series_code}:{period}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def ingest_macro_observation_candidate(
    session: AsyncSession,
    *,
    candidate: MacroObservationCandidate,
    metric_id: str,
    policy: ReconciliationPolicy,
    source_artifact_id: uuid.UUID,
    source_code: str,
    dataset_code: str,
    rights_profile_id: uuid.UUID,
    fetched_at: dt.datetime,
) -> IngestOutcome | MacroIngestSkipped:
    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return MacroIngestSkipped(
            reason=f"rights check denied 'store' for profile {rights_profile_id}"
        )

    subject_id = macro_series_subject_id(
        candidate.provider_code, candidate.dataset_code, candidate.series_code
    )
    key = macro_semantic_observation_key(
        source_code=source_code,
        dataset_code=dataset_code,
        series_code=candidate.series_code,
        period=candidate.period,
    )
    value = macro_observation_value(candidate)

    # A macro observation is valid for its entire reported period (a full
    # calendar year, for the annual pilot series) — a later year's figure
    # never supersedes an earlier year's; each period is its own fact,
    # same reasoning as a curve point's own calendar day or an FX rate's
    # own trading day. A REVISION to the same period's figure (WDI does
    # revise historical values) correctly does supersede, through the
    # normal exact-value-match reconciliation.
    period_start = dt.datetime.combine(candidate.period_start_day, dt.time.min, tzinfo=dt.UTC)
    period_end = dt.datetime.combine(candidate.period_end_day, dt.time.min, tzinfo=dt.UTC)
    valid_range: Range[dt.datetime] = Range(lower=period_start, upper=period_end, bounds="[)")

    return await ingest_and_reconcile(
        session,
        source_artifact_id=source_artifact_id,
        source_code=source_code,
        rights_profile_id=rights_profile_id,
        subject_type=SUBJECT_TYPE_MACRO_SERIES,
        subject_id=subject_id,
        metric_id=metric_id,
        semantic_observation_key=key,
        value=value,
        valid_from=candidate.period_start_day,
        valid_range=valid_range,
        fetched_at=fetched_at,
        policy=policy,
    )
