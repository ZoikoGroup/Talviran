"""evidence schema — source -> document -> version -> parsed version ->
chunk -> citation, and the EvidenceBundle/EvidenceMember that ties a
customer-visible claim back to its facts/calculations/documents (EVID-001).
Platform-wide: no RLS here.

EvidenceMember's accepted_fact_id now has a real FK — market.accepted_fact
was created in week 9 (this migration ALTER TABLEs the constraint on,
per expand-contract practice). calculation_result_id is still a plain
column — calculation.calculation_result doesn't exist until week 11; its
FK is added the same way once that table exists.

P4 (EVID-001 §3.1/§25) E0: DocumentVersion and ParsedDocumentVersion close
the identity-key separation the spec requires — DocumentID (logical
publication identity) is never the same id as DocumentVersionID (one
retrieved/published version, carrying its own rights_profile_id and the
market.source_artifact its raw bytes live in) or ParsedDocumentVersionID
(one parser run over one version — a re-parse with a new parser_version
is a new row, never an overwrite, so a historical citation always keeps
the parser version it was actually made against). DocumentChunk now
points at ParsedDocumentVersion, not Document directly (§11.2: a chunk is
parser-version-specific retrieval output, not a document-level fact) —
this table has never had a writer yet, so repointing its FK costs nothing
in migration risk.

Deliberately NOT added yet, because nothing in this slice writes or reads
them (same "don't add a column nothing uses" discipline as monitoring/
models.py): EvidenceRecord and ClaimEvidenceLink (EVID-001 §13.1/§16.1).
ClaimEvidenceLink specifically maps an AI-generated claim's text span back
to the evidence that supports it — meaningless before ai_gateway (P4b)
exists to produce a claim at all. EvidenceRecord's 8-state evidence_status
ladder (VERIFIED/PARTIAL/CONFLICT/STALE/SUPERSEDED/WITHDRAWN/QUARANTINED/
PURGED) is real, valuable EVID-001 doctrine, but retrofitting
EvidenceMember's already-working callers (evidence/service.py, monitoring/
alerts.py) to go through an extra EvidenceRecord layer belongs in the same
slice as whatever first needs to read that status back out, not before.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

# document_version.source_artifact_id and .rights_profile_id below declare
# cross-schema FKs by string - same import-resolution requirement as every
# other cross-schema FK in this codebase (see market/models.py's own
# identical comment): the module declaring the FK must guarantee its
# target is imported somewhere in the process first.
from app.modules.market import models as _market_models  # noqa: F401
from app.modules.rights import models as _rights_models  # noqa: F401

STATUS_DOCUMENT_VERSION_CURRENT = "CURRENT"
STATUS_DOCUMENT_VERSION_SUPERSEDED = "SUPERSEDED"
STATUS_DOCUMENT_VERSION_WITHDRAWN = "WITHDRAWN"

QUALITY_PASS = "PASS"
QUALITY_PARTIAL = "PARTIAL"
QUALITY_FAILED = "FAILED"
QUALITY_QUARANTINED = "QUARANTINED"

STATUS_JOB_PENDING = "PENDING"
STATUS_JOB_CLAIMED = "CLAIMED"
STATUS_JOB_DONE = "DONE"
STATUS_JOB_FAILED = "FAILED"

STAGE_ACQUIRE = "ACQUIRE"
STAGE_CLASSIFY = "CLASSIFY"
STAGE_PARSE = "PARSE"
STAGE_CHUNK = "CHUNK"
STAGE_INDEX = "INDEX"


class Document(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "document"
    __table_args__ = {"schema": "evidence"}

    # Nullable: a document isn't always tied to a market.source (e.g. a
    # user-uploaded document in a future workflow) — not an FK to
    # market.source for that reason, kept as a plain reference for now.
    source_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    title: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(120))


class DocumentVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One retrieved/published version of a Document (EVID-001 §4.1/§6).

    Immutable after acceptance except `status` (§6.2) — a new retrieval is
    always a new row (NEW_VERSION/RESTATEMENT/CORRECTION/SUPERSEDED in the
    spec's own event vocabulary), never an edit of this one.
    """

    __tablename__ = "document_version"
    __table_args__ = {"schema": "evidence"}

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.document.id"), index=True
    )
    # The actual acquired bytes for this version already have a home:
    # market.source_artifact (immutable, content-hashed, DATA-002 §3.1) is
    # the same SourceArtefact concept EVID-001 §3 names — not a new table.
    source_artifact_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.source_artifact.id"), index=True
    )
    # Non-null per EVID-001 §25.1 ("rights_profile_id non-null on
    # artefacts/chunks/evidence records") — a document's rights (store/
    # index/embed/ai/display/...) are evaluated independently of whatever
    # profile governs price data from the same source.
    rights_profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("governance.rights_profile.id")
    )
    version_label: Mapped[str | None] = mapped_column(String(200), default=None)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_DOCUMENT_VERSION_CURRENT)
    retrieved_at: Mapped[dt.datetime]
    published_at: Mapped[dt.datetime | None] = mapped_column(default=None)


class ParsedDocumentVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One parser run over one DocumentVersion (EVID-001 §8.1). A changed
    parser output is always a new row tied to its own parser_version —
    prior citations keep resolving against the parser version they were
    actually made with (§14.2), never silently repointed at a re-parse.
    """

    __tablename__ = "parsed_document_version"
    __table_args__ = {"schema": "evidence"}

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.document_version.id"), index=True
    )
    parser_name: Mapped[str] = mapped_column(String(100))
    parser_version: Mapped[str] = mapped_column(String(32))
    parse_started_at: Mapped[dt.datetime]
    parse_completed_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    language_codes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    page_count: Mapped[int | None] = mapped_column(default=None)
    # PASS/PARTIAL/FAILED/QUARANTINED (§8.3) - FAILED means no semantic
    # index admission at all; QUARANTINED means Ops review, same doctrine
    # as market/connectors/base.py's Quarantined candidate path.
    extraction_quality: Mapped[str] = mapped_column(String(16))
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)


class DocumentProcessingJob(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The out-of-process ingestion handoff (mirrors calculation.
    CalculationJob's identical shape/reasoning) - acquire/classify/parse/
    chunk/index run as claimed, out-of-process work, not synchronously in
    a request. Plain Postgres queue (FOR UPDATE SKIP LOCKED expected in
    the worker), not a broker.
    """

    __tablename__ = "document_processing_job"
    __table_args__ = {"schema": "evidence"}

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.document.id"), index=True
    )
    stage: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default=STATUS_JOB_PENDING, index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(1000), default=None)


class DocumentChunk(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Retrieval artefact only, never an evidence authority by itself
    (EVID-001 §11.1) — always traced back to its parsed document version +
    a citation_locator. Points at ParsedDocumentVersion, not Document
    directly: chunking is parser-version-specific output (§11.2), and a
    re-parse must not silently invalidate or renumber a prior chunk set.
    """

    __tablename__ = "document_chunk"
    __table_args__ = {"schema": "evidence"}

    parsed_document_version_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.parsed_document_version.id"), index=True
    )
    chunker_version: Mapped[str] = mapped_column(String(32))
    ordinal: Mapped[int] = mapped_column(Integer())
    text_content: Mapped[str] = mapped_column(String())
    page_start: Mapped[int | None] = mapped_column(default=None)
    page_end: Mapped[int | None] = mapped_column(default=None)
    token_estimate: Mapped[int | None] = mapped_column(default=None)
    content_hash: Mapped[str] = mapped_column(String(64))


class CitationLocator(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Resolves to an exact location within a document (page/bbox, text
    offsets, table cell, ...) — locator_data's shape depends on
    locator_type (EVID-001 §per-source-form), so it's JSONB rather than a
    rigid column set.
    """

    __tablename__ = "citation_locator"
    __table_args__ = {"schema": "evidence"}

    document_chunk_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.document_chunk.id"), index=True
    )
    locator_type: Mapped[str] = mapped_column(String(32))  # e.g. TEXT_OFFSET, PAGE_BBOX
    locator_data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class EvidenceBundle(UUIDPrimaryKeyMixin, Base):
    """Immutable once READY (EVID-001) — membership can't change after
    that. Enforcing immutability is application-level (P1 week 13, when
    something actually assembles one), not a DB constraint here.
    """

    __tablename__ = "evidence_bundle"
    __table_args__ = {"schema": "evidence"}

    purpose_type: Mapped[str] = mapped_column(String(64))
    knowledge_time: Mapped[dt.datetime]
    status: Mapped[str] = mapped_column(String(32), default="ASSEMBLING")
    # Not an FK: research.message is owned/migrated by the research module
    # (raw SQL, encrypted content) - see migration 0012's docstring for why
    # evidence.* doesn't take a cross-schema FK dependency on it.
    research_message_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), index=True, default=None
    )


class EvidenceMember(UUIDPrimaryKeyMixin, Base):
    """One row per evidence item inside a bundle — a discriminated union
    via `kind` + nullable FKs, exactly one of which is populated per row.
    """

    __tablename__ = "evidence_member"
    __table_args__ = {"schema": "evidence"}

    evidence_bundle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.evidence_bundle.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # FACT | CALCULATION | DOCUMENT_SPAN | ...

    accepted_fact_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.accepted_fact.id"), default=None
    )
    # No FK yet — calculation.calculation_result doesn't exist until week 11.
    calculation_result_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), default=None
    )
    document_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.document_chunk.id"), default=None
    )
    citation_locator_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.citation_locator.id"), default=None
    )
    source_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("market.source_artifact.id"), default=None
    )
