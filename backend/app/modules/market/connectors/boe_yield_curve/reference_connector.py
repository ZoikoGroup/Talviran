"""The Bank of England nominal gilt spot curve connector.

Deliberately does NOT resolve identity, compute an implied instrument
price, or write source_observation rows — that's identity-resolve +
observation-write + the curve-pricing calculation, downstream of this
connector (DATA-002's own pipeline ordering: acquire -> manifest ->
validate -> normalise -> identity-resolve -> observation-write ->
reconcile -> publish). This connector only covers acquire through
normalise, exactly like the DMO gilts connector.

See client.py's docstring for why this feed (not Tradeweb's per-instrument
prices) is the one automated here, and mapping.py's docstring for the
scope decisions on which sheets are parsed.
"""

import httpx

from app.modules.market.connectors.base import (
    AcquiredPayload,
    Checkpoint,
    CheckResult,
    DatasetDescriptor,
)
from app.modules.market.connectors.boe_yield_curve.client import (
    fetch_yield_curve_zip,
    now_utc,
)
from app.modules.market.connectors.boe_yield_curve.mapping import (
    CurvePointCandidate,
    RecordIssue,
    extract_nominal_workbook_bytes,
    parse_spot_curve,
)

DATASET_CODE = "boe.gilt-nominal-spot-curve"


class BoEYieldCurveConnector:
    dataset_code = DATASET_CODE

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_code=DATASET_CODE,
            description=(
                "Bank of England daily UK nominal government liability (gilt) "
                "spot curve. A fitted curve, not any specific instrument's "
                "traded price — published under the Open Government Licence v3.0."
            ),
        )

    async def acquire(self) -> AcquiredPayload:
        response = await fetch_yield_curve_zip(self._client)
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
        elif payload.raw_bytes[:2] != b"PK":
            reasons.append("response body is not a zip archive")
        return CheckResult(valid=not reasons, reasons=tuple(reasons))

    def identify_schema(self, payload: AcquiredPayload) -> CheckResult:
        workbook_bytes = extract_nominal_workbook_bytes(payload.raw_bytes)
        if isinstance(workbook_bytes, RecordIssue):
            return CheckResult(valid=False, reasons=(workbook_bytes.reason,))

        candidates = parse_spot_curve(workbook_bytes)
        if not any(isinstance(c, CurvePointCandidate) for c in candidates):
            return CheckResult(valid=False, reasons=("no curve points parsed from workbook",))
        return CheckResult(valid=True)

    def parse(self, payload: AcquiredPayload) -> list[CurvePointCandidate | RecordIssue]:
        workbook_bytes = extract_nominal_workbook_bytes(payload.raw_bytes)
        if isinstance(workbook_bytes, RecordIssue):
            return [workbook_bytes]
        return parse_spot_curve(workbook_bytes)

    def checkpoint(self, payload: AcquiredPayload) -> Checkpoint:
        candidates = self.parse(payload)
        dates = sorted(
            {c.curve_date for c in candidates if isinstance(c, CurvePointCandidate)}
        )
        token = dates[-1].isoformat() if dates else ""
        return Checkpoint(token=token)

    async def health(self) -> bool:
        try:
            payload = await self.acquire()
        except httpx.HTTPError:
            return False
        return self.verify_transport(payload).valid
