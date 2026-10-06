"""The evidence-bundle field contract for gilt_risk_metrics_v1, per
TAL-FI-GILT-001 Table 19 (docs/Talvrin_Gilt_Analytics_Methodology_Decision.docx)
- "Required persisted fields" for every displayed derived value, grouped
exactly as Table 19 groups them (identity / observed input / rights /
instrument master / convention / method / temporal / outputs / integrity).

Scope: this is the SHAPE a calculation_result row's `value` JSONB column
must hold for this spec once it's wired to persistence - not a persistence
call site itself. calculation/models.py's own docstring is explicit that
`value: JSONB` is deliberately schema-flexible per spec precisely so a new
spec doesn't need its own migration; this module is that per-spec shape,
built and tested as pure, serializable data, matching the same "validated
but unwired" scope the rest of this calc spec was deliberately left at
pending FIN-O3 (see implementation.py's and status.py's own docstrings).

Actual persistence (writing a calculation_result/calculation_input row)
lives in calculation/pipeline/gilt_risk_metrics_pricing.py, mirroring
curve_pricing.py's existing shape - this module stays the pure, DB-free
data contract; `bundle_to_jsonable` below is the one bridge between the
two (what that pipeline module stores in calculation_result.value).
"""

import datetime as dt
import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal

from app.modules.calculation.specs.gilt_risk_metrics_v1.implementation import RiskMetrics
from app.modules.calculation.specs.gilt_risk_metrics_v1.status import RiskMetricsStatus

#: TAL-FI-GILT-001's own version string (docs/Talvrin_Gilt_Analytics_
#: Methodology_Decision.docx Table 0) - recorded verbatim, not re-derived,
#: so a future methodology version bump is a one-line change here, not a
#: hunt through this module's prose.
METHODOLOGY_VERSION = "TAL-FI-GILT-001 v1.0"


@dataclass(frozen=True)
class ObservedInput:
    """Table 19 "observed input" row."""

    clean_price: Decimal
    price_currency: str
    source_dataset_id: str
    source_record_id: str
    source_effective_at: dt.datetime
    source_published_at: dt.datetime


@dataclass(frozen=True)
class RightsContext:
    """Table 19 "rights" row."""

    rights_policy_id: str
    entitlement_class: str
    export_allowed: bool
    redistribution_allowed: bool


@dataclass(frozen=True)
class InstrumentMaster:
    """Table 19 "instrument master" row."""

    isin: str
    coupon: Decimal
    issue_date: dt.date
    maturity_date: dt.date
    first_dividend_attributes: dict[str, str] | None
    master_data_source_id: str
    master_snapshot_hash: str


@dataclass(frozen=True)
class ConventionDerivedInputs:
    """Table 19 "convention" row."""

    settlement_date: dt.date
    calendar_version: str
    ex_dividend_state: bool
    accrued_interest: Decimal
    dirty_price: Decimal
    solved_yield: Decimal
    cashflow_schedule_hash: str


@dataclass(frozen=True)
class MethodMetadata:
    """Table 19 "method" row - DMO source pin + engine/config identity."""

    dmo_document_edition: str
    dmo_document_hash: str
    engine_build_hash: str
    calculation_config_hash: str
    methodology_version: str = METHODOLOGY_VERSION


@dataclass(frozen=True)
class TemporalLineage:
    """Table 19 "temporal" row - the tri-temporal pattern §4.1 of the
    methodology document requires (market/knowledge/system time), plus
    when this specific bundle was calculated and, if applicable, corrected.
    """

    market_valid_time: dt.datetime
    knowledge_time: dt.datetime
    ingested_at: dt.datetime
    calculated_at: dt.datetime
    corrected_at: dt.datetime | None = None


@dataclass(frozen=True)
class OutputValues:
    """Table 19 "outputs" row. macaulay_duration_full is included even
    though Table 19's own outputs row doesn't name it explicitly, because
    Table 10 is explicit that Macaulay Duration "may be computed/stored for
    diagnostics; not displayed in v1 summary UI" - stored, just not shown.
    """

    macaulay_duration_full: Decimal
    modified_duration_full: Decimal
    dv01_full: Decimal
    convexity_full: Decimal
    calculation_status: RiskMetricsStatus
    rounding_version: str


@dataclass(frozen=True)
class IntegrityMetadata:
    """Table 19 "integrity" row."""

    input_hash: str
    output_hash: str
    previous_bundle_id: uuid.UUID | None = None


@dataclass(frozen=True)
class GiltRiskMetricsEvidenceBundle:
    """One instance = one calculation_result.value JSONB payload for this
    spec. Field groups match TAL-FI-GILT-001 Table 19 exactly - "identity"
    is this dataclass's own top-level fields; the rest are Table 19's
    remaining 8 groups, one nested dataclass each.
    """

    evidence_bundle_id: uuid.UUID
    metric_id: str
    instrument_id: uuid.UUID
    observed_input: ObservedInput
    rights: RightsContext
    instrument_master: InstrumentMaster
    convention: ConventionDerivedInputs
    method: MethodMetadata
    temporal: TemporalLineage
    outputs: OutputValues
    integrity: IntegrityMetadata


def _canonical_hash(payload: Mapping[str, object]) -> str:
    """SHA-256 over a canonical (sorted-key, default=str) JSON encoding -
    same sha256-hex-digest convention golden_manifest.py uses for corpus
    integrity, applied here to evidence-bundle inputs/outputs instead of a
    corpus file.
    """
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_evidence_bundle(
    *,
    metric_id: str,
    instrument_id: uuid.UUID,
    observed_input: ObservedInput,
    rights: RightsContext,
    instrument_master: InstrumentMaster,
    convention: ConventionDerivedInputs,
    method: MethodMetadata,
    temporal: TemporalLineage,
    risk_metrics: RiskMetrics | None,
    calculation_status: RiskMetricsStatus,
    rounding_version: str,
    previous_bundle_id: uuid.UUID | None = None,
) -> GiltRiskMetricsEvidenceBundle:
    """Pure assembly - every piece of context must already be known to the
    caller (real instrument/source/rights/convention data); this function
    never invents a hash, timestamp, or identifier it wasn't given. A
    suppressed outcome (risk_metrics=None, per status.py's
    RiskMetricsOutcome) still produces a bundle - Table 13's suppression
    statuses are recorded outcomes, not an absence of evidence.
    """
    input_payload = {
        "observed_input": asdict(observed_input),
        "instrument_master": asdict(instrument_master),
        "convention": asdict(convention),
        "method": asdict(method),
    }
    input_hash = _canonical_hash(input_payload)

    if risk_metrics is None:
        output_payload: dict[str, object] = {"calculation_status": calculation_status.value}
        outputs = OutputValues(
            macaulay_duration_full=Decimal(0),
            modified_duration_full=Decimal(0),
            dv01_full=Decimal(0),
            convexity_full=Decimal(0),
            calculation_status=calculation_status,
            rounding_version=rounding_version,
        )
    else:
        output_payload = {
            "macaulay_duration_full": str(risk_metrics.macaulay_duration),
            "modified_duration_full": str(risk_metrics.modified_duration),
            "dv01_full": str(risk_metrics.dv01),
            "convexity_full": str(risk_metrics.convexity),
            "calculation_status": calculation_status.value,
        }
        outputs = OutputValues(
            macaulay_duration_full=risk_metrics.macaulay_duration,
            modified_duration_full=risk_metrics.modified_duration,
            dv01_full=risk_metrics.dv01,
            convexity_full=risk_metrics.convexity,
            calculation_status=calculation_status,
            rounding_version=rounding_version,
        )
    output_hash = _canonical_hash(output_payload)

    return GiltRiskMetricsEvidenceBundle(
        evidence_bundle_id=uuid.uuid4(),
        metric_id=metric_id,
        instrument_id=instrument_id,
        observed_input=observed_input,
        rights=rights,
        instrument_master=instrument_master,
        convention=convention,
        method=method,
        temporal=temporal,
        outputs=outputs,
        integrity=IntegrityMetadata(
            input_hash=input_hash,
            output_hash=output_hash,
            previous_bundle_id=previous_bundle_id,
        ),
    )


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal | dt.date | dt.datetime | uuid.UUID):
        return str(value)
    if isinstance(value, RiskMetricsStatus):
        return value.value
    return value


def bundle_to_jsonable(bundle: GiltRiskMetricsEvidenceBundle) -> dict[str, object]:
    """The exact dict calculation_result.value (JSONB) stores for this
    spec - every Table 19 field, stringified where JSON has no native
    type (Decimal/date/datetime/UUID/enum), nothing dropped or summarized.
    """
    return _json_safe(asdict(bundle))  # type: ignore[return-value]
