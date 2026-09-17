"""Populates real market.accepted_fact rows in the dev database — the layer
seed_dev.py deliberately does NOT create (it only seeds the reference
catalog: issuer/instrument/alias/terms). accepted_fact only exists once the
real ingestion pipeline actually runs, exactly as it would in production;
this script runs that same pipeline against dev-appropriate sources so
manual testing (e.g. POST /api/v1/research with a gilt-facts query) has
real data to show, rather than always hitting the fail-safe "no reconciled
data yet" fallback.

Run with (after `uv run python -m scripts.seed_dev`):

    uv run python -m scripts.ingest_dev_data

Idempotent: re-running just re-confirms NO_CHANGE for unchanged data.
Every integration test run TRUNCATEs market.accepted_fact as part of test
isolation (tests/integration/conftest.py) — re-run this script afterward if
you want to manually exercise the API again.
"""

import asyncio
import datetime as dt
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.db import get_session_factory
from app.modules.calculation.models import CalculationSpecification
from app.modules.calculation.pipeline.job_queue import (
    enqueue_model_implied_price_job,
    run_next_job,
)
from app.modules.market.connectors.base import AcquiredPayload, Quarantined, validate_and_parse
from app.modules.market.connectors.boe_yield_curve.mapping import CurvePointCandidate
from app.modules.market.connectors.boe_yield_curve.reference_connector import (
    BoEYieldCurveConnector,
)
from app.modules.market.connectors.dmo_gilts.mapping import RecordIssue
from app.modules.market.connectors.dmo_gilts.reference_connector import DMOGiltsReferenceConnector
from app.modules.market.models import Dataset, Source, SourceArtifact
from app.modules.market.pipeline.curve_ingest import ingest_curve_point_candidate
from app.modules.market.pipeline.stages import ingest_gilt_reference_candidate
from app.modules.reference.models import InstrumentAlias
from app.modules.rights.models import RightsProfile
from scripts.seed_dev import SEED_GILT_ISIN

_GILT_PRICE_FROM_CURVE_SPEC_CODE = "gilt_price_from_curve_v1"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
DMO_FIXTURE_PATH = _BACKEND_ROOT / "tests" / "fixtures" / "dmo_gilts_in_issue.xml"
BOE_FIXTURE_PATH = _BACKEND_ROOT / "tests" / "fixtures" / "boe_yield_curve_latest.zip"


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        instrument_id = (
            await session.execute(
                select(InstrumentAlias.instrument_id).where(
                    InstrumentAlias.alias_type == "ISIN",
                    InstrumentAlias.alias_value == SEED_GILT_ISIN,
                )
            )
        ).scalar_one_or_none()
        if instrument_id is None:
            raise SystemExit(
                "No seeded instrument found - run `uv run python -m scripts.seed_dev` first."
            )

        dmo_rights = (
            await session.execute(select(RightsProfile).where(RightsProfile.code == "uk-dmo.gilts"))
        ).scalar_one()
        boe_rights = (
            await session.execute(
                select(RightsProfile).where(RightsProfile.code == "boe.yield-curve")
            )
        ).scalar_one()

        # --- reference terms, from the real captured DMO fixture ---
        source = Source(code=f"uk-dmo-dev-{uuid.uuid4().hex[:6]}", name="UK DMO (dev)")
        session.add(source)
        await session.flush()
        dataset = Dataset(source_id=source.id, code="gilts-in-issue", name="Gilts in Issue")
        session.add(dataset)
        await session.flush()
        dmo_artifact = SourceArtifact(
            dataset_id=dataset.id, sha256="1" * 64, storage_ref="dev-fixture://dmo",
            media_type="text/xml", byte_length=len(DMO_FIXTURE_PATH.read_bytes()),
            retrieved_at=dt.datetime.now(dt.UTC),
        )
        session.add(dmo_artifact)
        await session.flush()

        dmo_connector = DMOGiltsReferenceConnector(httpx.AsyncClient())
        dmo_payload = AcquiredPayload(
            raw_bytes=DMO_FIXTURE_PATH.read_bytes(), content_type="text/xml", status_code=200,
            fetched_at=dt.datetime.now(dt.UTC), source_url="dev-fixture",
        )
        # validate_and_parse, not connector.parse() directly - a connector's
        # own transport/schema checks (DATA-002 §7) are useless if nothing
        # ever calls them before parsing (see connectors/base.py's docstring).
        candidates_or_quarantine = validate_and_parse(dmo_connector, dmo_payload)
        if isinstance(candidates_or_quarantine, Quarantined):
            raise SystemExit(f"DMO payload quarantined: {candidates_or_quarantine.reasons}")
        candidates = candidates_or_quarantine
        seed_candidate = next(
            c for c in candidates if not isinstance(c, RecordIssue) and c.isin == SEED_GILT_ISIN
        )
        ref_result = await ingest_gilt_reference_candidate(
            session, candidate=seed_candidate, source_artifact_id=dmo_artifact.id,
            source_code="uk-dmo", dataset_code="gilts-in-issue",
            rights_profile_id=dmo_rights.id, fetched_at=dmo_payload.fetched_at,
        )
        await session.commit()
        print(f"Reference terms: {ref_result}")

        # --- BoE curve: try live first, fall back to the real captured fixture ---
        boe_connector = BoEYieldCurveConnector(httpx.AsyncClient())
        try:
            boe_payload = await boe_connector.acquire()
            if not boe_connector.verify_transport(boe_payload).valid:
                raise ValueError("live fetch returned an unexpected payload")
            print("BoE curve: fetched live.")
        except Exception as exc:  # noqa: BLE001 - any live-fetch problem falls back, doesn't crash
            print(f"BoE curve: live fetch unavailable ({exc}), using the captured fixture.")
            boe_payload = AcquiredPayload(
                raw_bytes=BOE_FIXTURE_PATH.read_bytes(),
                content_type="application/x-zip-compressed",
                status_code=200, fetched_at=dt.datetime.now(dt.UTC), source_url="dev-fixture",
            )

        boe_source = Source(code=f"boe-dev-{uuid.uuid4().hex[:6]}", name="BoE (dev)")
        session.add(boe_source)
        await session.flush()
        boe_dataset = Dataset(
            source_id=boe_source.id, code="gilt-nominal-spot-curve", name="Gilt Nominal Spot Curve"
        )
        session.add(boe_dataset)
        await session.flush()
        boe_artifact = SourceArtifact(
            dataset_id=boe_dataset.id, sha256="2" * 64, storage_ref="dev://boe",
            media_type="application/x-zip-compressed", byte_length=len(boe_payload.raw_bytes),
            retrieved_at=dt.datetime.now(dt.UTC),
        )
        session.add(boe_artifact)
        await session.flush()

        boe_candidates_or_quarantine = validate_and_parse(boe_connector, boe_payload)
        if isinstance(boe_candidates_or_quarantine, Quarantined):
            raise SystemExit(f"BoE payload quarantined: {boe_candidates_or_quarantine.reasons}")
        boe_candidates = boe_candidates_or_quarantine
        points = [c for c in boe_candidates if isinstance(c, CurvePointCandidate)]
        latest_date = max(p.curve_date for p in points)
        latest_points = [p for p in points if p.curve_date == latest_date]
        for point in latest_points:
            await ingest_curve_point_candidate(
                session, candidate=point, source_artifact_id=boe_artifact.id,
                source_code="boe", dataset_code="gilt-nominal-spot-curve",
                rights_profile_id=boe_rights.id, fetched_at=boe_payload.fetched_at,
            )
        await session.commit()
        print(f"BoE curve: ingested {len(latest_points)} points for {latest_date}.")

        # Enqueue + drain rather than calling compute_and_persist_model_implied_price
        # directly in-process (P2's job-table handoff - see
        # app/modules/calculation/pipeline/job_queue.py). If the spec isn't
        # APPROVED yet (scripts.approve_calculation_spec hasn't been run),
        # the job still runs to completion and records why it was skipped -
        # that's the correct fail-closed outcome, not a script error.
        spec = (
            await session.execute(
                select(CalculationSpecification).where(
                    CalculationSpecification.code == _GILT_PRICE_FROM_CURVE_SPEC_CODE
                )
            )
        ).scalar_one_or_none()
        if spec is None:
            print(
                f"No {_GILT_PRICE_FROM_CURVE_SPEC_CODE} calculation_specification found - "
                "run scripts.seed_dev first. Skipping pricing job."
            )
            return

        await enqueue_model_implied_price_job(
            session, instrument_id=instrument_id, as_of_date=latest_date,
            calculation_specification_id=spec.id,
        )
        await session.commit()

        result = await run_next_job(session)
        if result is not None:
            print(f"Pricing job: {result.outcome}")


if __name__ == "__main__":
    asyncio.run(main())
