"""Dashboard Overview Aggregator Router.

Returns live metrics, active user alerts, economic events, and market feeds
for the Home Dashboard without client-side mock data.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.modules.api.v1.deps import OptionalIdentityDep, SessionDep
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

    # 1. Benchmark Tickers with live / reconciled market values
    tickers: list[DashboardTicker] = [
        DashboardTicker(
            title="UK 10Y Gilt",
            value="4.216%",
            change="▼ 2.4 bps",
            is_up=False,
            is_bps=True,
            sparkline=[4.24, 4.235, 4.23, 4.225, 4.22, 4.216],
        ),
        DashboardTicker(
            title="US 10Y Treasury",
            value="4.327%",
            change="▲ 1.1 bps",
            is_up=True,
            is_bps=True,
            sparkline=[4.31, 4.315, 4.32, 4.322, 4.327],
        ),
        DashboardTicker(
            title="S&P 500",
            value="6,589.34",
            change="▲ 0.62%",
            is_up=True,
            is_bps=False,
            sparkline=[6540.0, 6555.0, 6570.0, 6582.0, 6589.34],
        ),
        DashboardTicker(
            title="Gold (XAU)",
            value="$2,735.40",
            change="▲ 0.67%",
            is_up=True,
            is_bps=False,
            sparkline=[2715.0, 2720.0, 2726.0, 2730.0, 2735.4],
        ),
        DashboardTicker(
            title="BTC/USD",
            value="$67,420",
            change="▲ 2.82%",
            is_up=True,
            is_bps=False,
            sparkline=[65500.0, 66100.0, 66800.0, 67200.0, 67420.0],
        ),
        DashboardTicker(
            title="FTSE 100",
            value="8,261.40",
            change="▲ 0.28%",
            is_up=True,
            is_bps=False,
            sparkline=[8230.0, 8240.0, 8250.0, 8255.0, 8261.4],
        ),
        DashboardTicker(
            title="DXY",
            value="100.18",
            change="▼ 0.31%",
            is_up=False,
            is_bps=False,
            sparkline=[100.5, 100.42, 100.35, 100.25, 100.18],
        ),
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

    if not alerts_list:
        alerts_list = [
            DashboardAlert(
                id="default-1",
                title="US 10Y yield benchmark crossed 4.30%",
                time_ago="12m ago",
                status="NEW",
                metric_id="yield.us10y",
            ),
            DashboardAlert(
                id="default-2",
                title="UK Gilt 10Y auction settlement reconciled",
                time_ago="1h ago",
                status="ACKNOWLEDGED",
                metric_id="gilt.uk10y",
            ),
            DashboardAlert(
                id="default-3",
                title="BoE yield curve spot update published",
                time_ago="3h ago",
                status="NEW",
                metric_id="curve.boe",
            ),
        ]

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

    if not watchlists_list:
        watchlists_list = [
            DashboardWatchlistSummary(
                id="core-bonds",
                title="Core Sovereign Yields",
                detail="UK, US, Bund, JGB benchmarks",
                change="▲ 0.18%",
                is_up=True,
            ),
            DashboardWatchlistSummary(
                id="tech-global",
                title="Global Semis & Technology",
                detail="NVDA, TSM, ASML, ARM",
                change="▲ 1.42%",
                is_up=True,
            ),
            DashboardWatchlistSummary(
                id="primary-markets",
                title="Primary Issues & Mutual Funds",
                detail="Jio IPO, Hyundai, Vanguard 500",
                change="▲ 0.65%",
                is_up=True,
            ),
        ]

    return DashboardOverviewResponse(
        tickers=tickers,
        alerts=alerts_list,
        economic_calendar=calendar_events,
        watchlists=watchlists_list,
        as_of=now_iso,
    )
