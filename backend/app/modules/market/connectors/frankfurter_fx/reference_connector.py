"""The Frankfurter currency-exchange-rate connector.

Deliberately does NOT derive a subject_id, resolve identity, or write
source_observation rows — that's app.modules.market.pipeline.fx_ingest's
job, downstream of this connector, following the same acquire -> manifest
-> validate -> normalise -> identity-resolve -> observation-write ->
reconcile -> publish ordering as the existing gilt and curve connectors.

Frankfurter serves rates for one base currency against one or more quote
currencies per call — dataset_code identifies the FEED (Frankfurter's
rates endpoint), not any one specific base/quote query, so covering
several pilot pairs across multiple distinct base currencies means several
connector instances/acquisitions, the same reasoning the DMO connector
uses for covering many gilts from one feed.
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
from app.modules.market.connectors.frankfurter_fx.client import fetch_rates, now_utc
from app.modules.market.connectors.frankfurter_fx.mapping import (
    FxRateCandidate,
    RecordIssue,
    parse_rates,
)

DATASET_CODE = "frankfurter.rates"


class FrankfurterFxConnector:
    dataset_code = DATASET_CODE

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_currency: str,
        quote_currencies: tuple[str, ...],
    ) -> None:
        self._client = client
        self._base_currency = base_currency
        self._quote_currencies = quote_currencies

    async def discover(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_code=DATASET_CODE,
            description=(
                "Frankfurter exchange rates, blended from central-bank sources "
                "including the ECB. Free, public, no API key."
            ),
        )

    async def acquire(self) -> AcquiredPayload:
        response = await fetch_rates(
            self._client,
            base_currency=self._base_currency,
            quote_currencies=self._quote_currencies,
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
        if payload.status_code != 200:
            reasons.append(f"unexpected status code: {payload.status_code}")
        if not payload.raw_bytes:
            reasons.append("empty response body")
        elif "json" not in payload.content_type.lower():
            reasons.append(f"unexpected content-type: {payload.content_type!r}")
        return CheckResult(valid=not reasons, reasons=tuple(reasons))

    def _decode(self, payload: AcquiredPayload) -> Any:
        return json.loads(payload.raw_bytes)

    def identify_schema(self, payload: AcquiredPayload) -> CheckResult:
        try:
            body = self._decode(payload)
        except json.JSONDecodeError as exc:
            return CheckResult(valid=False, reasons=(f"not valid JSON: {exc}",))

        if not isinstance(body, list):
            return CheckResult(
                valid=False, reasons=(f"expected a JSON array, got {type(body).__name__}",)
            )

        candidates = parse_rates(body)
        if not any(isinstance(c, FxRateCandidate) for c in candidates):
            return CheckResult(valid=False, reasons=("no rate records parsed from response",))
        return CheckResult(valid=True)

    def parse(self, payload: AcquiredPayload) -> list[FxRateCandidate | RecordIssue]:
        return parse_rates(self._decode(payload))

    def checkpoint(self, payload: AcquiredPayload) -> Checkpoint:
        candidates = self.parse(payload)
        dates = sorted({c.as_of for c in candidates if isinstance(c, FxRateCandidate)})
        token = dates[-1].isoformat() if dates else ""
        return Checkpoint(token=token)

    async def health(self) -> bool:
        try:
            payload = await self.acquire()
        except httpx.HTTPError:
            return False
        return self.verify_transport(payload).valid
