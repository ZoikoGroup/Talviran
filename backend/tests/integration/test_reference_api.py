"""End-to-end HTTP tests for the reference read endpoints — proves the full
stack together (FastAPI route -> PDP -> rights engine -> pagination -> DB),
not just the service-layer pieces already covered by
test_reference_pagination.py and test_policy_pdp.py.

Uses httpx.AsyncClient with ASGITransport (NOT fastapi.testclient.TestClient)
deliberately: TestClient drives the ASGI app through its own anyio portal —
effectively a second, separate event loop — which would hand db_session's
asyncpg connection to two different loops in the same test, exactly the
"Event loop is closed" class of bug already fixed once in conftest.py.
ASGITransport runs the app in-process on the *same* loop as the test
coroutine, so db_session stays valid throughout.
"""

import datetime as dt
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.main import create_app
from app.modules.policy.models import ActivationRecord, CapabilityStatus
from app.modules.reference.service import REFERENCE_RIGHTS_PROFILE_CODE
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
            capability_code="reference.issuers.read", jurisdiction_code=None, status="AVAILABLE"
        )
    )
    session.add(
        CapabilityStatus(
            capability_code="reference.instruments.read",
            jurisdiction_code=None,
            status="AVAILABLE",
        )
    )
    session.add(
        ActivationRecord(
            jurisdiction_code="GB",
            operating_entity="Test Entity",
            status="ACTIVE",
            effective_from=dt.datetime.now(dt.UTC) - dt.timedelta(days=1),
            effective_to=None,
        )
    )
    profile = RightsProfile(code=REFERENCE_RIGHTS_PROFILE_CODE, status="ACTIVE")
    session.add(profile)
    await session.flush()
    session.add(
        RightsGrant(rights_profile_id=profile.id, action="retrieve", permission_state="ALLOW")
    )
    await session.flush()


async def test_issuers_endpoint_denies_before_governance_is_seeded(
    client: httpx.AsyncClient,
) -> None:
    # Correct default: nothing is registered as available yet, so the PDP
    # denies — proving the endpoint fails closed rather than defaulting open.
    response = await client.get("/api/v1/issuers")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_BLOCKED"


async def test_instruments_endpoint_denies_before_governance_is_seeded(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/instruments")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_BLOCKED"


async def test_issuers_endpoint_permits_after_governance_is_seeded(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_governance(db_session)

    response = await client.get("/api/v1/issuers")
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None, "has_more": False}


async def test_instruments_endpoint_permits_after_governance_is_seeded(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_governance(db_session)

    response = await client.get("/api/v1/instruments")
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None, "has_more": False}


async def test_issuers_endpoint_rejects_invalid_limit(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_governance(db_session)

    response = await client.get("/api/v1/issuers", params={"limit": 0})
    assert response.status_code == 422
