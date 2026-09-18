"""The Twelve Data equity end-of-day price connector.

Deliberately does NOT resolve identity or write source_observation rows —
that's app.modules.market.pipeline.equity_ingest's job, downstream of this
connector, following the same acquire -> manifest -> validate -> normalise
-> identity-resolve -> observation-write -> reconcile -> publish ordering
as the existing gilt connector (the only other connector needing identity
resolution).

One instance tracks exactly one (symbol, exchange) pair — covering the
pilot list means one instance per stock, the same reasoning the
Frankfurter connector uses for covering several currency pairs.
"""

import json
from typing import Any

import httpx

from app.modules.market.connectors.base import (
    AcquiredPayload,
    Checkpoint,
    CheckResult,
    DatasetDescriptor,
)
from app.modules.market.connectors.twelve_data_equity.client import (
    fetch_daily_series,
    now_utc,
)
from app.modules.market.connectors.twelve_data_equity.mapping import (
    EquityEodPriceCandidate,
    RecordIssue,
    parse_time_series,
)

DATASET_CODE = "twelve-data.eod-price"


class TwelveDataEquityConnector:
    dataset_code = DATASET_CODE

    def __init__(
        self, client: httpx.AsyncClient, *, symbol: str, exchange: str, api_key: str
    ) -> None:
        self._client = client
        self._symbol = symbol
        self._exchange = exchange
        self._api_key = api_key

    async def discover(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_code=DATASET_CODE,
            description=(
                f"Twelve Data end-of-day price for {self._symbol} on "
                f"{self._exchange}. Free tier is end-of-day only, not real-time."
            ),
        )

    async def acquire(self) -> AcquiredPayload:
        response = await fetch_daily_series(
            self._client, symbol=self._symbol, exchange=self._exchange, api_key=self._api_key
        )
        return AcquiredPayload(
            raw_bytes=response.content,
            content_type=response.headers.get("content-type", ""),
            status_code=response.status_code,
            fetched_at=now_utc(),
            source_url=str(response.request.url) if response.request else "",
        )

    def verify_transport(self, payload: AcquiredPayload) -> CheckResult:
        reasons: list[str] = []
        if not payload.raw_bytes:
            reasons.append("empty response body")
        elif "json" not in payload.content_type.lower():
            reasons.append(f"unexpected content-type: {payload.content_type!r}")
        # Deliberately NOT checking status_code != 200 here: Twelve Data
        # can return a symbol-level error with HTTP 200 and an embedded
        # status:"error" body (see mapping.py's docstring) — that's a
        # schema-level rejection, handled in identify_schema below, not a
        # transport failure.
        return CheckResult(valid=not reasons, reasons=tuple(reasons))

    def _decode(self, payload: AcquiredPayload) -> Any:
        return json.loads(payload.raw_bytes)

    def identify_schema(self, payload: AcquiredPayload) -> CheckResult:
        try:
            body = self._decode(payload)
        except json.JSONDecodeError as exc:
            return CheckResult(valid=False, reasons=(f"not valid JSON: {exc}",))

        if not isinstance(body, dict):
            return CheckResult(
                valid=False, reasons=(f"expected a JSON object, got {type(body).__name__}",)
            )

        if body.get("status") == "error":
            return CheckResult(
                valid=False,
                reasons=(f"Twelve Data error {body.get('code')!r}: {body.get('message')!r}",),
            )

        candidates = parse_time_series(body, symbol=self._symbol, exchange=self._exchange)
        if not any(isinstance(c, EquityEodPriceCandidate) for c in candidates):
            reasons = tuple(c.reason for c in candidates if isinstance(c, RecordIssue))
            return CheckResult(
                valid=False, reasons=reasons or ("no price rows parsed from response",)
            )
        return CheckResult(valid=True)

    def parse(self, payload: AcquiredPayload) -> list[EquityEodPriceCandidate | RecordIssue]:
        return parse_time_series(
            self._decode(payload), symbol=self._symbol, exchange=self._exchange
        )

    def checkpoint(self, payload: AcquiredPayload) -> Checkpoint:
        candidates = self.parse(payload)
        dates = sorted(
            {c.trade_date for c in candidates if isinstance(c, EquityEodPriceCandidate)}
        )
        token = dates[-1].isoformat() if dates else ""
        return Checkpoint(token=token)

    async def health(self) -> bool:
        try:
            payload = await self.acquire()
        except httpx.HTTPError:
            return False
        return self.verify_transport(payload).valid
