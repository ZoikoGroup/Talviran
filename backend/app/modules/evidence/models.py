"""evidence schema — source -> document -> chunk -> citation, and the
EvidenceBundle/EvidenceMember that ties a customer-visible claim back to
its facts/calculations/documents (EVID-001). Platform-wide: no RLS here.

EvidenceMember's accepted_fact_id now has a real FK — market.accepted_fact
was created in week 9 (this migration ALTER TABLEs the constraint on,
per expand-contract practice). calculation_result_id is still a plain
column — calculation.calculation_result doesn't exist until week 11; its
FK is added the same way once that table exists.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "document"
    __table_args__ = {"schema": "evidence"}

    # Nullable: a document isn't always tied to a market.source (e.g. a
    # user-uploaded document in a future workflow) — not an FK to
    # market.source for that reason, kept as a plain reference for now.
    source_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    title: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(120))


class DocumentChunk(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Retrieval artefact only, never an evidence authority by itself
    (EVID-001) — always traced back to its document + a citation_locator.
    """

    __tablename__ = "document_chunk"
    __table_args__ = {"schema": "evidence"}

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.document.id"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer())
    text_content: Mapped[str] = mapped_column(String())


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
