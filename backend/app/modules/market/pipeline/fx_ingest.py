"""Orchestrates one FxRateCandidate (Frankfurter connector output) through
the pipeline stages this module owns: rights check -> observation write ->
reconcile/publish. Acquire/manifest/validate/normalise already happened in
the connector before a candidate ever reaches here — same division of
labour as curve_ingest.py's yield-curve-point path.

Identity resolution is deliberately skipped here, for the same reason it's
skipped for a curve point: a currency pair (e.g. "GBP/INR") carries no
identity ambiguity to resolve — it comes directly from two fixed ISO 4217
codes, not from matching free text against a catalogue — so subject_id is
a fixed, deterministic UUID5 derived from the pair itself. An FX pair is
also not naturally an "instrument with an issuer", so it deliberately
never touches reference.instrument at all.
"""

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market.connectors.frankfurter_fx.mapping import FxRateCandidate
from app.modules.market.pipeline.ingest_tail import IngestOutcome, ingest_and_reconcile
from app.modules.market.pipeline.reconciliation_policy import FX_SPOT_RATE_POLICY
from app.modules.rights.engine import RightsDecision, evaluate_action

METRIC_FX_SPOT_RATE = "FX_SPOT_RATE"
SUBJECT_TYPE_FX_PAIR = "FX_PAIR"

# Fixed, never regenerate: changing this would silently orphan every
# previously-published FX fact under a new, unrelated subject_id.
_FX_PAIR_NAMESPACE = uuid.UUID("b6bb4544-7b30-4ff7-9c07-a73bcbf95454")


def fx_pair_subject_id(base_currency: str, quote_currency: str) -> uuid.UUID:
    return uuid.uuid5(_FX_PAIR_NAMESPACE, f"FX:{base_currency.upper()}:{quote_currency.upper()}")


@dataclass(frozen=True)
class FxIngestSkipped:
    reason: str


def fx_rate_value(candidate: FxRateCandidate) -> dict[str, str]:
    # base/quote are redundant with subject_id (a one-way uuid5 hash of
    # them) but a fact must be self-describing to a reader — nothing should
    # have to reverse-engineer a hash to know what a fact even means.
    return {
        "base_currency": candidate.base_currency,
        "quote_currency": candidate.quote_currency,
        "rate": str(candidate.rate),
    }


def fx_semantic_observation_key(
    *,
    source_code: str,
    dataset_code: str,
    base_currency: str,
    quote_currency: str,
    as_of: dt.date,
) -> str:
    raw = f"{source_code}:{dataset_code}:{base_currency}:{quote_currency}:{as_of.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def ingest_fx_rate_candidate(
    session: AsyncSession,
    *,
    candidate: FxRateCandidate,
    source_artifact_id: uuid.UUID,
    source_code: str,
    dataset_code: str,
    rights_profile_id: uuid.UUID,
    fetched_at: dt.datetime,
) -> IngestOutcome | FxIngestSkipped:
    rights_decision = await evaluate_action(session, "store", rights_profile_id)
    if rights_decision != RightsDecision.ALLOW:
        return FxIngestSkipped(
            reason=f"rights check denied 'store' for profile {rights_profile_id}"
        )

    subject_id = fx_pair_subject_id(candidate.base_currency, candidate.quote_currency)
    key = fx_semantic_observation_key(
        source_code=source_code,
        dataset_code=dataset_code,
        base_currency=candidate.base_currency,
        quote_currency=candidate.quote_currency,
        as_of=candidate.as_of,
    )
    value = fx_rate_value(candidate)

    # An FX rate is valid for exactly its own calendar day — the next day's
    # rate is a different real-world fact, not a correction of this one.
    day_start = dt.datetime.combine(candidate.as_of, dt.time.min, tzinfo=dt.UTC)
    valid_range: Range[dt.datetime] = Range(
        lower=day_start, upper=day_start + dt.timedelta(days=1), bounds="[)"
    )

    return await ingest_and_reconcile(
        session,
        source_artifact_id=source_artifact_id,
        source_code=source_code,
        rights_profile_id=rights_profile_id,
        subject_type=SUBJECT_TYPE_FX_PAIR,
        subject_id=subject_id,
        metric_id=METRIC_FX_SPOT_RATE,
        semantic_observation_key=key,
        value=value,
        valid_from=candidate.as_of,
        valid_range=valid_range,
        fetched_at=fetched_at,
        policy=FX_SPOT_RATE_POLICY,
    )
