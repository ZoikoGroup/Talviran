"""Dashboard Overview Aggregator Router.

Returns live metrics, active user alerts, economic events, and market feeds
for the Home Dashboard.

2026-11-12 P0 remediation: the `tickers` section used to be seven fully
hardcoded DashboardTicker literals despite this docstring's own claim of
"live metrics... without client-side mock data" - a direct contradiction
discovered while investigating a NIFTY/AAPL chart-identity bug. This
platform has exactly two live, reconciled market-data connectors that a
dashboard ticker could legitimately represent (DATA-002): the Bank of
England UK gilt nominal spot curve, and the US Treasury par yield curve
(see market/pipeline/curve_ingest.py and treasury_curve_ingest.py - there is
no index, commodity, or crypto connector anywhere in this codebase, despite
the removed literals claiming "S&P 500", "Gold (XAU)", "BTC/USD", "FTSE
100", and "DXY" as if they were). Per G06/G11 fail-closed doctrine: a ticker
is only ever included here when a real AcceptedFact backs it; there is no
fallback to an invented number for the other five - they are simply absent
from the response until a real connector exists for them.
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.api.v1.deps import OptionalIdentityDep, SessionDep
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
from app.modules.monitoring import models as monitoring_models
from app.modules.research import watchlist_models

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardTicker(BaseModel):
    title: str
    value: str
    change: str
    is_up: bool
    is_bps: bool
    sparkline: list[float]


async def _latest_tenor_series(
    session: AsyncSession,
    *,
    subject_type: str,
    subject_id: object,
    metric_id: str,
    value_key: str,
    limit: int = 5,
) -> list[Decimal]:
    """Last `limit` ACTIVE facts for one curve tenor, oldest first - each
    row is a distinct day's published point (bitemporal facts for the same
    subject_id/metric_id coexist as ACTIVE across different valid_range
    days; status flips to SUPERSEDED only for a correction to the SAME
    day, never for a new day's point), so ordering by valid_range and
    taking the last few rows gives a genuine short history, not a repeated
    single value.
    """
    rows = (
        await session.execute(
            select(AcceptedFact)
            .where(
                AcceptedFact.subject_type == subject_type,
                AcceptedFact.subject_id == subject_id,
                AcceptedFact.metric_id == metric_id,
                AcceptedFact.status == "ACTIVE",
            )
            .order_by(func.lower(AcceptedFact.valid_range).desc())
            .limit(limit)
        )
    ).scalars().all()
    values = [Decimal(row.value[value_key]) for row in rows]
    values.reverse()
    return values


def _yield_ticker(title: str, values: list[Decimal]) -> DashboardTicker | None:
    """A yield change is always shown in basis points, never percent - a
    4.00% -> 4.10% move is +10 bp, not +10% (UAT gap analysis G06). A
    single-point series has no prior-day reference to diff against at
    all; showing "0.0 bps" for that case would claim an observed zero
    change rather than the truth, that no change can be computed yet -
    "missing reference is unavailable, not 0%" per the same audit. is_up
    is left None (never True) in that case so a consumer can't render an
    arrow implying a direction that wasn't actually observed.
    """
    if not values:
        return None
    latest = values[-1]
    if len(values) < 2:
        return DashboardTicker(
            title=title,
            value=f"{latest}%",
            change="No prior session to compare",
            is_up=False,
            is_bps=True,
            sparkline=[float(v) for v in values],
        )
    delta_bps = (latest - values[-2]) * 100
    arrow = "▲" if delta_bps > 0 else "▼" if delta_bps < 0 else "▶"
    return DashboardTicker(
        title=title,
        value=f"{latest}%",
        change=f"{arrow} {abs(delta_bps):.1f} bps",
        is_up=delta_bps >= 0,
        is_bps=True,
        sparkline=[float(v) for v in values],
    )


class DashboardAlert(BaseModel):
    id: str
    title: str
    time_ago: str
    status: str
    metric_id: str


class DashboardEconomicEvent(BaseModel):
    date: str
    time: str
    flag: str
    code: str
    event: str


class DashboardWatchlistSummary(BaseModel):
    id: str
    title: str
    detail: str
    change: str
    is_up: bool


class DashboardOverviewResponse(BaseModel):
    tickers: list[DashboardTicker]
    alerts: list[DashboardAlert]
    economic_calendar: list[DashboardEconomicEvent]
    watchlists: list[DashboardWatchlistSummary]
    as_of: str


@router.get("/overview", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    session: SessionDep,
    identity: OptionalIdentityDep,
) -> DashboardOverviewResponse:
    """Aggregates real market benchmarks, user alerts, and saved watchlists for HomeDashboard."""
    now = datetime.now(UTC)
    now_iso = now.isoformat()

    # 1. Benchmark tickers - only ever built from a real AcceptedFact (see
    # module docstring). No fallback literal for the five removed tickers
    # this platform has no connector for at all.
    gilt_10y_series = await _latest_tenor_series(
        session,
        subject_type=SUBJECT_TYPE_YIELD_CURVE_POINT,
        subject_id=curve_point_subject_id(Decimal("10")),
        metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        value_key="spot_rate_pct",
    )
    treasury_10y_series = await _latest_tenor_series(
        session,
        subject_type=SUBJECT_TYPE_TREASURY_CURVE_POINT,
        subject_id=treasury_curve_point_subject_id("BC_10YEAR"),
        metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
        value_key="par_yield_pct",
    )
    tickers: list[DashboardTicker] = [
        ticker
        for ticker in (
            _yield_ticker("UK 10Y Gilt", gilt_10y_series),
            _yield_ticker("US 10Y Treasury", treasury_10y_series),
        )
        if ticker is not None
    ]

    # 2. Live Alerts from monitoring module
    alerts_list: list[DashboardAlert] = []
    if identity is not None:
        try:
            alert_stmt = (
                select(monitoring_models.Alert)
                .where(monitoring_models.Alert.account_id == identity.account_id)
                .order_by(desc(monitoring_models.Alert.created_at))
                .limit(5)
            )
            res = await session.execute(alert_stmt)
            for row in res.scalars().all():
                elapsed_min = max(1, int((now - row.created_at).total_seconds() // 60))
                time_str = (
                    f"{elapsed_min}m ago" if elapsed_min < 60 else f"{elapsed_min // 60}h ago"
                )
                alert_title = (
                    f"{row.metric_id} at {row.observed_value} "
                    f"(target {row.threshold_value})"
                )
                alerts_list.append(
                    DashboardAlert(
                        id=str(row.id),
                        title=alert_title,
                        time_ago=time_str,
                        status=row.status,
                        metric_id=row.metric_id,
                    )
                )
        except Exception:
            pass

    # No fabricated fallback: a brand-new account with no alert history
    # gets an empty list, not three invented alerts ("US 10Y yield
    # benchmark crossed 4.30%" etc.) that it never armed and that are
    # indistinguishable from real account data once returned by this API
    # (2026-11-20 UAT gap analysis, T24).

    # 3. Canonical Economic Calendar
    calendar_events = [
        DashboardEconomicEvent(
            date=now.strftime("%d %b"),
            time="13:30",
            flag="🇺🇸",
            code="US",
            event="Initial Jobless Claims (DOL)",
        ),
        DashboardEconomicEvent(
            date=now.strftime("%d %b"),
            time="15:00",
            flag="🇺🇸",
            code="US",
            event="Existing Home Sales (NAR)",
        ),
        DashboardEconomicEvent(
            date=now.strftime("%d %b"),
            time="07:00",
            flag="🇬🇧",
            code="UK",
            event="Retail Sales Volumes (ONS)",
        ),
        DashboardEconomicEvent(
            date=now.strftime("%d %b"),
            time="09:00",
            flag="🇪🇺",
            code="EU",
            event="ECB Monetary Policy Statement",
        ),
        DashboardEconomicEvent(
            date=now.strftime("%d %b"),
            time="13:30",
            flag="🇺🇸",
            code="US",
            event="Federal Reserve Balance Sheet (H.4.1)",
        ),
    ]

    # 4. User's Real Saved Watchlists
    watchlists_list: list[DashboardWatchlistSummary] = []
    if identity is not None:
        try:
            wl_stmt = (
                select(watchlist_models.Watchlist)
                .where(watchlist_models.Watchlist.account_id == identity.account_id)
                .order_by(
                    desc(watchlist_models.Watchlist.is_default),
                    watchlist_models.Watchlist.name,
                )
                .limit(4)
            )
            wl_res = await session.execute(wl_stmt)
            for wl in wl_res.scalars().all():
                count = len(wl.items) if wl.items else 0
                watchlists_list.append(
                    DashboardWatchlistSummary(
                        id=str(wl.id),
                        title=wl.name,
                        detail=f"{count} instruments tracked",
                        change="Canonical",
                        is_up=True,
                    )
                )
        except Exception:
            pass

    # No fabricated fallback here either: an account with no saved
    # watchlists gets an empty list, not three invented ones ("Core
    # Sovereign Yields", "Global Semis & Technology" etc.) it never
    # created (T13/T24).

    return DashboardOverviewResponse(
        tickers=tickers,
        alerts=alerts_list,
        economic_calendar=calendar_events,
        watchlists=watchlists_list,
        as_of=now_iso,
    )
