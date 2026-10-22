"""The US Treasury daily par yield curve connector.

Deliberately does NOT resolve identity, compute a derived value, or write
source_observation rows — that's identity-resolve + observation-write,
downstream of this connector (DATA-002's own pipeline ordering: acquire ->
manifest -> validate -> normalise -> identity-resolve -> observation-write
-> reconcile -> publish). This connector only covers acquire through
normalise, exactly like the BoE yield curve connector it mirrors.

See client.py's docstring for why home.treasury.gov's own feed is used
(not api.fiscaldata.treasury.gov, which only carries average rates on
outstanding debt — a different dataset), and mapping.py's docstring for
the BC_30YEARDISPLAY scope decision.
"""

import httpx
from defusedxml import ElementTree as safe_ET  # type: ignore[import-untyped]

from app.modules.market.connectors.base import (
    AcquiredPayload,
    Checkpoint,
    CheckResult,
    DatasetDescriptor,
)
from app.modules.market.connectors.treasury_yield_curve.client import (
    fetch_yield_curve_xml,
    now_utc,
)
from app.modules.market.connectors.treasury_yield_curve.mapping import (
    CurvePointCandidate,
    RecordIssue,
    parse_yield_curve,
)

DATASET_CODE = "treasury.par-yield-curve"
_ATOM_NS = "http://www.w3.org/2005/Atom"


class TreasuryYieldCurveConnector:
    dataset_code = DATASET_CODE

    def __init__(self, client: httpx.AsyncClient, *, year: int | None = None) -> None:
        self._client = client
        # None means "current year at acquire() time" - fixed to a specific
        # year only when a caller (e.g. a test replaying a captured fixture
        # for a past year) needs one.
        self._year = year

    async def discover(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_code=DATASET_CODE,
            description=(
                "US Treasury daily par yield curve (constant maturity "
                "Treasury rates) — published by home.treasury.gov."
            ),
        )

    async def acquire(self) -> AcquiredPayload:
        year = self._year if self._year is not None else now_utc().year
        response = await fetch_yield_curve_xml(self._client, year=year)
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
        elif payload.raw_bytes[:5] != b"<?xml":
            reasons.append("response body is not an XML document")
        return CheckResult(valid=not reasons, reasons=tuple(reasons))

    def identify_schema(self, payload: AcquiredPayload) -> CheckResult:
        try:
            root = safe_ET.fromstring(payload.raw_bytes)
        except Exception as exc:  # noqa: BLE001 - any parse failure means QUARANTINED, not a crash
            return CheckResult(valid=False, reasons=(f"not well-formed XML: {exc}",))

        if root.tag != f"{{{_ATOM_NS}}}feed":
            return CheckResult(valid=False, reasons=(f"unexpected root element: {root.tag!r}",))

        candidates = parse_yield_curve(payload.raw_bytes)
        if not any(isinstance(c, CurvePointCandidate) for c in candidates):
            return CheckResult(valid=False, reasons=("no curve points parsed from feed",))
        return CheckResult(valid=True)

    def parse(self, payload: AcquiredPayload) -> list[CurvePointCandidate | RecordIssue]:
        return parse_yield_curve(payload.raw_bytes)

    def checkpoint(self, payload: AcquiredPayload) -> Checkpoint:
        candidates = self.parse(payload)
        dates = sorted({c.curve_date for c in candidates if isinstance(c, CurvePointCandidate)})
        token = dates[-1].isoformat() if dates else ""
        return Checkpoint(token=token)

    async def health(self) -> bool:
        try:
            payload = await self.acquire()
        except httpx.HTTPError:
            return False
        return self.verify_transport(payload).valid
