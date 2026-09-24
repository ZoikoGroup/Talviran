"""Embeds every chunk of the GEMM Guidebook PDF scripts.parse_gemm_guidebook
already parsed. Mirrors scripts.embed_methodology_doc's exact pattern.

Run with (after `uv run python -m scripts.parse_gemm_guidebook`):

    uv run python -m scripts.embed_gemm_guidebook
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
from scripts.ingest_gemm_guidebook import DOCUMENT_TITLE


async def main() -> None:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY not set")

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
                    .where(Document.title == DOCUMENT_TITLE)
                )
            )
            .scalars()
            .all()
        )
        if not chunk_ids:
            raise SystemExit(
                "no document_chunk rows found — run "
                "`uv run python -m scripts.parse_gemm_guidebook` first"
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
