"""GET /api/v1/dashboard/overview - proves the ticker section is built from
real AcceptedFact rows, not the hardcoded literals it used to return (G06
remediation, 2026-11-12). Uses httpx.AsyncClient + ASGITransport, not
fastapi.testclient.TestClient, for the same event-loop reason documented in
test_reference_api.py's own docstring.
"""

import datetime as dt
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest_asyncio
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.main import create_app
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.market.pipeline.treasury_curve_ingest import (
    METRIC_US_TREASURY_PAR_YIELD_CURVE,
    SUBJECT_TYPE_TREASURY_CURVE_POINT,
    treasury_curve_point_subject_id,
)

_GILT_SUBJECT_ID = curve_point_subject_id(Decimal("10"))
_TREASURY_SUBJECT_ID = treasury_curve_point_subject_id("BC_10YEAR")


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _fact_range(valid_on: dt.date) -> tuple[Range[dt.datetime], Range[dt.datetime]]:
    valid_range = Range(
        lower=dt.datetime.combine(valid_on, dt.time.min, tzinfo=dt.UTC),
        upper=dt.datetime.combine(valid_on + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC),
        bounds="[)",
    )
    knowledge_range = Range(
        lower=dt.datetime.combine(valid_on, dt.time(8), tzinfo=dt.UTC), upper=None, bounds="[)"
    )
    return valid_range, knowledge_range


async def test_overview_has_no_tickers_when_no_real_data_exists(
    client: httpx.AsyncClient,
) -> None:
    """The removed literals (S&P 500, Gold, BTC/USD, FTSE 100, DXY) must
    never come back, in any form, for any instrument this platform has no
    connector for - and with zero seeded curve facts, the two genuinely
    connectable tickers (gilt/treasury 10Y) must be honestly absent too,
    not silently defaulted to an invented number.
    """
    response = await client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tickers"] == []
    titles = {t["title"] for t in body["tickers"]}
    for forbidden in ("S&P 500", "Gold (XAU)", "BTC/USD", "FTSE 100", "DXY"):
        assert forbidden not in titles


async def test_overview_ticker_reflects_real_seeded_curve_fact(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """Seed a real UK 10Y gilt AcceptedFact and a real US 10Y Treasury
    AcceptedFact directly (the only two tickers this endpoint may ever
    show) and assert the response's numbers trace back to exactly those
    rows - never a hardcoded literal.
    """
    valid_range, knowledge_range = _fact_range(dt.date(2026, 11, 10))
    db_session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
            subject_id=_GILT_SUBJECT_ID,
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            valid_range=valid_range,
            knowledge_range=knowledge_range,
            value={"tenor_years": "10", "spot_rate_pct": "4.123"},
            status="ACTIVE",
        )
    )
    db_session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_TREASURY_CURVE_POINT,
            subject_id=_TREASURY_SUBJECT_ID,
            metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
            valid_range=valid_range,
            knowledge_range=knowledge_range,
            value={
                "tenor_field": "BC_10YEAR",
                "tenor_label": "10 Year",
                "par_yield_pct": "4.456",
            },
            status="ACTIVE",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200, response.text
    tickers_by_title = {t["title"]: t for t in response.json()["tickers"]}

    assert tickers_by_title["UK 10Y Gilt"]["value"] == "4.123%"
    assert tickers_by_title["US 10Y Treasury"]["value"] == "4.456%"
    # Still must never resurrect any of the removed, unconnected tickers.
    for forbidden in ("S&P 500", "Gold (XAU)", "BTC/USD", "FTSE 100", "DXY"):
        assert forbidden not in tickers_by_title


# ------------------------------------------------------------------
# G06 (UAT gap analysis): frozen golden cases for the yield-change math -
# "4.00% -> 4.10% is +10 bp, not +10%" is a numerical invariant, not a
# rendering detail, so it gets an independently-computed expected value
# per case rather than a loose "looks plausible" assertion.
# ------------------------------------------------------------------


async def test_yield_change_is_shown_in_basis_points_not_percent(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """4.00% -> 4.10% is a +10 bp move. Independently computed: 100 * (4.10
    - 4.00) = 10.0. Must never render as "+10%" or "+0.1%" - both would be
    a real, distinct financial-reporting error a reader could act on.
    """
    yesterday, today = _fact_range(dt.date(2026, 11, 9)), _fact_range(dt.date(2026, 11, 10))
    db_session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
            subject_id=_GILT_SUBJECT_ID,
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            valid_range=yesterday[0],
            knowledge_range=yesterday[1],
            value={"tenor_years": "10", "spot_rate_pct": "4.00"},
            status="ACTIVE",
        )
    )
    db_session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
            subject_id=_GILT_SUBJECT_ID,
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            valid_range=today[0],
            knowledge_range=today[1],
            value={"tenor_years": "10", "spot_rate_pct": "4.10"},
            status="ACTIVE",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200, response.text
    ticker = {t["title"]: t for t in response.json()["tickers"]}["UK 10Y Gilt"]

    assert ticker["change"] == "▲ 10.0 bps"
    assert ticker["is_up"] is True
    assert "%" not in ticker["change"], "a yield move must never be expressed in percent"


async def test_a_downward_yield_move_is_shown_as_negative_bps(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """4.10% -> 4.00% is independently computed as -10 bp."""
    yesterday, today = _fact_range(dt.date(2026, 11, 9)), _fact_range(dt.date(2026, 11, 10))
    db_session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_TREASURY_CURVE_POINT,
            subject_id=_TREASURY_SUBJECT_ID,
            metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
            valid_range=yesterday[0],
            knowledge_range=yesterday[1],
            value={"tenor_field": "BC_10YEAR", "tenor_label": "10 Year", "par_yield_pct": "4.10"},
            status="ACTIVE",
        )
    )
    db_session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_TREASURY_CURVE_POINT,
            subject_id=_TREASURY_SUBJECT_ID,
            metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
            valid_range=today[0],
            knowledge_range=today[1],
            value={"tenor_field": "BC_10YEAR", "tenor_label": "10 Year", "par_yield_pct": "4.00"},
            status="ACTIVE",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200, response.text
    ticker = {t["title"]: t for t in response.json()["tickers"]}["US 10Y Treasury"]

    assert ticker["change"] == "▼ 10.0 bps"
    assert ticker["is_up"] is False


async def test_a_single_days_fact_shows_no_fabricated_zero_change(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """Section 09 of the UAT gap analysis, verbatim: 'Missing reference is
    unavailable, not 0%.' A single data point has no prior session to diff
    against - the old code computed delta_bps=0 in that case, which reads
    as an observed zero move rather than the truth: no comparison is
    possible yet. Must say so honestly instead.
    """
    only_day = _fact_range(dt.date(2026, 11, 10))
    db_session.add(
        AcceptedFact(
            subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
            subject_id=_GILT_SUBJECT_ID,
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            valid_range=only_day[0],
            knowledge_range=only_day[1],
            value={"tenor_years": "10", "spot_rate_pct": "4.123"},
            status="ACTIVE",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200, response.text
    ticker = {t["title"]: t for t in response.json()["tickers"]}["UK 10Y Gilt"]

    assert "bps" not in ticker["change"]
    assert "0.0" not in ticker["change"]
    assert ticker["change"] == "No prior session to compare"
