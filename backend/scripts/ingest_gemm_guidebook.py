"""Acquires the real UK DMO GEMM Guidebook PDF ("A guide to the roles of
the DMO and Primary Dealers (GEMMs) in the UK government bond market") -
a second, genuinely different real document, growing the evidence
corpus beyond the single yield-conventions PDF (5 chunks) it was
calibrated against. Mirrors scripts.ingest_methodology_doc's exact
pattern.

Run with (after `uv run python -m scripts.seed_dev`):

    uv run python -m scripts.ingest_gemm_guidebook

Idempotent: re-running with byte-identical content reuses the existing
DocumentVersion rather than creating a duplicate.
"""

import asyncio
import datetime as dt

import httpx
from sqlalchemy import select

from app.core.db import get_session_factory
from app.modules.evidence.connectors.dmo_methodology.client import (
    fetch_gemm_guidebook_pdf,
    now_utc,
)
from app.modules.evidence.pipeline.acquire import AcquisitionRejected, acquire_document
from app.modules.rights.models import RightsProfile
from scripts.seed_dev import UK_DMO_METHODOLOGY_RIGHTS_PROFILE_CODE

DOCUMENT_TITLE = (
    "UK DMO — GEMM Guidebook: roles of the DMO and Primary Dealers "
    "(guidebook200921.pdf)"
)
# The edition date printed in the document's own filename/title.
_PUBLISHED_AT = dt.datetime(2021, 9, 20, tzinfo=dt.UTC)


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        rights_profile_id = (
            await session.execute(
                select(RightsProfile.id).where(
                    RightsProfile.code == UK_DMO_METHODOLOGY_RIGHTS_PROFILE_CODE
                )
            )
        ).scalar_one_or_none()
        if rights_profile_id is None:
            raise SystemExit(
                f"rights_profile {UK_DMO_METHODOLOGY_RIGHTS_PROFILE_CODE!r} not seeded — "
                "run `uv run python -m scripts.seed_dev` first"
            )

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await fetch_gemm_guidebook_pdf(client)
        response.raise_for_status()

        result = await acquire_document(
            session,
            content=response.content,
            media_type=response.headers.get("content-type", "").split(";")[0].strip(),
            document_title=DOCUMENT_TITLE,
            source_code="uk-dmo",
            source_name="UK Debt Management Office",
            dataset_code="methodology-docs",
            dataset_name="Methodology Documents",
            rights_profile_id=rights_profile_id,
            published_at=_PUBLISHED_AT,
            retrieved_at=now_utc(),
        )
        await session.commit()

        if isinstance(result, AcquisitionRejected):
            raise SystemExit(f"acquisition rejected: {result.reason}")

        print(f"document_id            = {result.document_id}")
        print(f"document_version_id    = {result.document_version_id}")
        print(f"source_artifact_id     = {result.source_artifact_id}")
        print(f"was_new_artifact       = {result.was_new_artifact}")
        print(f"bytes acquired         = {len(response.content)}")


if __name__ == "__main__":
    asyncio.run(main())
