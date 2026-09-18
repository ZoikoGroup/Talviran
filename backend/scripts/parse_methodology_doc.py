"""Parses the methodology PDF scripts.ingest_methodology_doc acquired -
EVID-001 E2, proven against the real, live-acquired document, not a
synthetic fixture.

Run with (after `uv run python -m scripts.ingest_methodology_doc`):

    uv run python -m scripts.parse_methodology_doc
"""

import asyncio

from sqlalchemy import select

from app.core.db import get_session_factory
from app.modules.evidence.models import Document, DocumentVersion
from app.modules.evidence.pipeline.parse import ParseRejected, parse_document_version
from scripts.ingest_methodology_doc import _DOCUMENT_TITLE


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        document_version_id = (
            await session.execute(
                select(DocumentVersion.id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(Document.title == _DOCUMENT_TITLE)
                .order_by(DocumentVersion.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if document_version_id is None:
            raise SystemExit(
                "no document_version found — run "
                "`uv run python -m scripts.ingest_methodology_doc` first"
            )

        result = await parse_document_version(session, document_version_id=document_version_id)
        await session.commit()

        if isinstance(result, ParseRejected):
            raise SystemExit(f"parse rejected: {result.reason}")

        print(f"parsed_document_version_id = {result.parsed_document_version_id}")
        print(f"extraction_quality         = {result.extraction_quality}")
        print(f"chunk_count                = {result.chunk_count}")
        print(f"warnings                   = {result.warnings}")


if __name__ == "__main__":
    asyncio.run(main())
