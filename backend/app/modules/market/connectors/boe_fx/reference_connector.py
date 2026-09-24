"""The Bank of England GBP/USD spot-rate connector. Deliberately does NOT
derive a subject_id, resolve identity, or write source_observation rows -
that's app.modules.market.pipeline.fx_ingest's job downstream of this
connector, same acquire -> manifest -> validate -> normalise -> ... chain
every other connector in this codebase follows.

One instance, one pair (GBP/USD) - BoE's IADB serves one series per query,
unlike Frankfurter's one-base-many-quotes shape, so there's no equivalent
"several pilot pairs from one feed" concern here.
"""

import httpx

from app.modules.market.connectors.base import (
    AcquiredPayload,
    Checkpoint,
    CheckResult,
    DatasetDescriptor,
)
from app.modules.market.connectors.boe_fx.client import fetch_gbp_usd_spot_rates, now_utc
from app.modules.market.connectors.boe_fx.mapping import parse_rows
from app.modules.market.connectors.frankfurter_fx.mapping import FxRateCandidate, RecordIssue

DATASET_CODE = "boe.fx-daily-spot-rates"


class BoEFxConnector:
    dataset_code = DATASET_CODE

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_code=DATASET_CODE,
            description=(
                "Bank of England daily GBP/USD spot exchange rate (Interactive "
                "Statistical Database, series XUDLUSS). Free, public, OGL v3.0, "
                "no API key."
            ),
        )

    async def acquire(self) -> AcquiredPayload:
        response = await fetch_gbp_usd_spot_rates(self._client)
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
        return CheckResult(valid=not reasons, reasons=tuple(reasons))

    def _decode(self, payload: AcquiredPayload) -> str:
        return payload.raw_bytes.decode("utf-8-sig")

    def identify_schema(self, payload: AcquiredPayload) -> CheckResult:
        candidates = parse_rows(self._decode(payload))
        if not any(isinstance(c, FxRateCandidate) for c in candidates):
            return CheckResult(valid=False, reasons=("no rate rows parsed from response",))
        return CheckResult(valid=True)

    def parse(self, payload: AcquiredPayload) -> list[FxRateCandidate | RecordIssue]:
        return parse_rows(self._decode(payload))

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
