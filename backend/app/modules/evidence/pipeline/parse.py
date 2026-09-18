"""EVID-001 E2 (parsing/structural extraction) - turns an acquired
DocumentVersion's stored bytes into a ParsedDocumentVersion + ordered
DocumentChunks. `pypdf` for text extraction: pure-Python, no system
binary dependency (this machine has no poppler/pandoc — the same reason
the docs-estate .docx specs are read via python-docx, not a converter).

Chunking here is page-level only for this slice: EVID-001 §8.2's full
hierarchy (page -> section/heading -> paragraph -> table -> footnote) is
real structural-extraction work nothing before this needed; a page
boundary is still a genuine structural unit (§11.1: "boundaries should
respect structural units over arbitrary token counts"), just the
coarsest one — not a placeholder chunking strategy. Heading/paragraph/
table-aware chunking is a real follow-up, not silently dropped scope:
every chunk already keeps its page_start/page_end regardless of what
finer structure lands later, so nothing here needs to change shape when
it does.

FAILED extraction quality (§8.3) means no semantic index admission at
all - a FAILED ParsedDocumentVersion gets zero chunks, on purpose.
"""

import datetime as dt
import hashlib
import io
import uuid
from dataclasses import dataclass, field

import pypdf
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import (
    QUALITY_FAILED,
    QUALITY_PARTIAL,
    QUALITY_PASS,
    DocumentChunk,
    DocumentVersion,
    ParsedDocumentVersion,
)
from app.modules.market import artifact_storage
from app.modules.market.models import SourceArtifact

PARSER_NAME = "pypdf"
CHUNKER_VERSION = "page-v1"


def _parser_version() -> str:
    return pypdf.__version__


@dataclass(frozen=True)
class ParseRejected:
    reason: str


@dataclass(frozen=True)
class ParseResult:
    parsed_document_version_id: uuid.UUID
    chunk_count: int
    extraction_quality: str
    warnings: list[str] = field(default_factory=list)


async def parse_document_version(
    session: AsyncSession, *, document_version_id: uuid.UUID
) -> ParseResult | ParseRejected:
    version = await session.get(DocumentVersion, document_version_id)
    if version is None:
        return ParseRejected(reason=f"no document_version {document_version_id}")

    artifact = await session.get(SourceArtifact, version.source_artifact_id)
    if artifact is None:
        return ParseRejected(reason="source_artifact missing for this document_version")

    try:
        content = artifact_storage.load(artifact.storage_ref)
    except FileNotFoundError:
        return ParseRejected(
            reason=f"stored bytes not found for storage_ref {artifact.storage_ref!r}"
        )

    started_at = dt.datetime.now(dt.UTC)
    try:
        reader = PdfReader(io.BytesIO(content))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except PyPdfError as exc:
        parsed = ParsedDocumentVersion(
            document_version_id=version.id,
            parser_name=PARSER_NAME,
            parser_version=_parser_version(),
            parse_started_at=started_at,
            parse_completed_at=dt.datetime.now(dt.UTC),
            language_codes=[],
            page_count=None,
            extraction_quality=QUALITY_FAILED,
            warnings=[f"pypdf could not read this file: {exc}"],
        )
        session.add(parsed)
        await session.flush()
        return ParseResult(
            parsed_document_version_id=parsed.id,
            chunk_count=0,
            extraction_quality=QUALITY_FAILED,
            warnings=parsed.warnings,
        )

    warnings: list[str] = []
    non_empty_pages = [(i, t) for i, t in enumerate(page_texts) if t.strip()]
    if not non_empty_pages:
        quality = QUALITY_FAILED
        warnings.append("no extractable text on any page")
    elif len(non_empty_pages) < len(page_texts):
        quality = QUALITY_PARTIAL
        warnings.append(
            f"{len(page_texts) - len(non_empty_pages)} of {len(page_texts)} pages had no "
            "extractable text (likely scanned/image content - OCR is a separate, later slice)"
        )
    else:
        quality = QUALITY_PASS

    parsed = ParsedDocumentVersion(
        document_version_id=version.id,
        parser_name=PARSER_NAME,
        parser_version=_parser_version(),
        parse_started_at=started_at,
        parse_completed_at=dt.datetime.now(dt.UTC),
        # No language-detection library wired up this slice - DMO's own
        # documents are published in English only, so this is an explicit,
        # documented simplification, not a silent guess at generality.
        language_codes=["en"],
        page_count=len(page_texts),
        extraction_quality=quality,
        warnings=warnings,
    )
    session.add(parsed)
    await session.flush()

    if quality != QUALITY_FAILED:
        for ordinal, (page_index, text) in enumerate(non_empty_pages):
            session.add(
                DocumentChunk(
                    parsed_document_version_id=parsed.id,
                    chunker_version=CHUNKER_VERSION,
                    ordinal=ordinal,
                    text_content=text,
                    page_start=page_index + 1,
                    page_end=page_index + 1,
                    token_estimate=len(text.split()),
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                )
            )
        await session.flush()

    return ParseResult(
        parsed_document_version_id=parsed.id,
        chunk_count=len(non_empty_pages) if quality != QUALITY_FAILED else 0,
        extraction_quality=quality,
        warnings=warnings,
    )
