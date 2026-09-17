"""End-to-end HTTP tests for GET /api/v1/calculations - same shape as
test_reference_api.py (PDP fail-closed by default, permits once governance
is seeded), plus the detail endpoint's evidence-input drill-down and its
own not-found handling.
"""

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.main import create_app
from app.modules.calculation.models import (
    BASIS_MODEL_IMPLIED,
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.service import CALCULATION_RIGHTS_PROFILE_CODE
from app.modules.market.models import AcceptedFact
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.rights.models import RightsGrant, RightsProfile


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_governance(session: AsyncSession) -> None:
    session.add(
        CapabilityStatus(
            capability_code="calculation.results.read", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    session.add(
        ActivationRecord(
            jurisdiction_code="GB", operating_entity="Test Entity", status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1), effective_to=None,
        )
    )
    profile = RightsProfile(code=CALCULATION_RIGHTS_PROFILE_CODE, status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(
        RightsGrant(rights_profile_id=profile.id, action="retrieve", permission_state="ALLOW")
    )
    await session.flush()


async def _seed_calculation_result(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (calculation_result_id, subject_id)."""
    spec = CalculationSpecification(
        code=f"test-spec-{uuid.uuid4().hex[:8]}", version="1", status="DRAFT", description="test",
    )
    session.add(spec)
    await session.flush()

    fact = AcceptedFact(
        subject_type="INSTRUMENT", subject_id=uuid.uuid4(), metric_id="TEST_METRIC",
        valid_range=Range(lower=dt.datetime(2020, 1, 1, tzinfo=dt.UTC), upper=None, bounds="[)"),
        knowledge_range=Range(lower=dt.datetime.now(dt.UTC), upper=None, bounds="[)"),
        value={"a": "1"}, status="ACTIVE",
    )
    session.add(fact)
    await session.flush()

    subject_id = uuid.uuid4()
    result = CalculationResult(
        calculation_specification_id=spec.id, subject_type="INSTRUMENT", subject_id=subject_id,
        metric_id="MODEL_IMPLIED_CLEAN_PRICE", as_of_date=dt.date(2026, 9, 15),
        basis=BASIS_MODEL_IMPLIED, value={"clean_price": "92.39"}, status="ACTIVE",
    )
    session.add(result)
    await session.flush()

    session.add(
        CalculationInput(calculation_result_id=result.id, accepted_fact_id=fact.id, role="FACT")
    )
    await session.commit()
    return result.id, subject_id


async def test_list_denies_before_governance_is_seeded(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/calculations")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_BLOCKED"


async def test_detail_denies_before_governance_is_seeded(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/v1/calculations/{uuid.uuid4()}")
    assert response.status_code == 403


async def test_list_permits_and_returns_empty_after_governance_is_seeded(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_governance(db_session)
    response = await client.get("/api/v1/calculations")
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None, "has_more": False}


async def test_list_returns_a_real_seeded_result(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_governance(db_session)
    result_id, subject_id = await _seed_calculation_result(db_session)

    response = await client.get("/api/v1/calculations")
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == str(result_id)
    assert body["items"][0]["basis"] == BASIS_MODEL_IMPLIED
    assert body["items"][0]["value"] == {"clean_price": "92.39"}

    filtered = await client.get("/api/v1/calculations", params={"subject_id": str(subject_id)})
    assert filtered.status_code == 200
    assert len(filtered.json()["items"]) == 1

    filtered_out = await client.get(
        "/api/v1/calculations", params={"subject_id": str(uuid.uuid4())}
    )
    assert filtered_out.json()["items"] == []


async def test_detail_returns_full_evidence_trail(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_governance(db_session)
    result_id, _ = await _seed_calculation_result(db_session)

    response = await client.get(f"/api/v1/calculations/{result_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(result_id)
    assert len(body["inputs"]) == 1
    assert body["inputs"][0]["role"] == "FACT"


async def test_detail_unknown_id_is_not_found(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_governance(db_session)
    response = await client.get(f"/api/v1/calculations/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_rejects_invalid_limit(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_governance(db_session)
    response = await client.get("/api/v1/calculations", params={"limit": 0})
    assert response.status_code == 422
