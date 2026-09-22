"""Embeds every chunk of the methodology PDF scripts.parse_methodology_doc
already parsed - EVID-001 E3 semantic half, proven against real,
live-acquired data.

Run with (after `uv run python -m scripts.parse_methodology_doc`):

    uv run python -m scripts.embed_methodology_doc
"""

import asyncio

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.modules.evidence.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    ParsedDocumentVersion,
)
from app.modules.evidence.pipeline.embed import EmbedRejected, embed_chunk
from scripts.ingest_methodology_doc import _DOCUMENT_TITLE


async def main() -> None:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY not set in .env")

    factory = get_session_factory()
    async with factory() as session:
        chunk_ids = (
            (
                await session.execute(
                    select(DocumentChunk.id)
                    .join(
                        ParsedDocumentVersion,
                        ParsedDocumentVersion.id == DocumentChunk.parsed_document_version_id,
                    )
                    .join(
                        DocumentVersion,
                        DocumentVersion.id == ParsedDocumentVersion.document_version_id,
                    )
                    .join(Document, Document.id == DocumentVersion.document_id)
                    .where(Document.title == _DOCUMENT_TITLE)
                )
            )
            .scalars()
            .all()
        )
        if not chunk_ids:
            raise SystemExit(
                "no document_chunk rows found — run "
                "`uv run python -m scripts.parse_methodology_doc` first"
            )

        async with httpx.AsyncClient() as http:
            for chunk_id in chunk_ids:
                result = await embed_chunk(
                    session, chunk_id=chunk_id, http=http, api_key=settings.gemini_api_key
                )
                await session.commit()
                if isinstance(result, EmbedRejected):
                    print(f"{chunk_id}: REJECTED - {result.reason}")
                else:
                    print(f"{chunk_id}: embedded")


if __name__ == "__main__":
    asyncio.run(main())
