"""The TreasuryDirect auctioned-securities connector — covers Note, Bond
and TIPS queries (see mapping.py's own docstring for why Bills/FRNs are
out of scope here).

Deliberately does NOT resolve identity or write reference.instrument/
source_observation rows — that split is the same one DMO gilts uses:
scripts/onboard_all_treasury_securities.py is the controlled onboarding
action (creates reference.instrument/alias/FiSovereignTerms), and
pipeline/treasury_securities_ingest.py is the identity-resolve +
observation-write + reconcile step downstream of THAT. This connector only
covers acquire through normalise.
"""

import json

import httpx

from app.modules.market.connectors.base import (
    AcquiredPayload,
    Checkpoint,
    CheckResult,
    DatasetDescriptor,
)
from app.modules.market.connectors.treasury_securities.client import (
    fetch_auctioned_securities,
    now_utc,
)
from app.modules.market.connectors.treasury_securities.mapping import (
    RecordIssue,
    TreasurySecurityCandidate,
    parse_auctioned_securities,
)

DATASET_CODE = "treasurydirect.auctioned-securities"

#: A real pilot of currently-active securities, not an attempt at the full
#: historical CUSIP universe - 10 years comfortably covers every Note/Bond
#: still outstanding today plus several TIPS reopenings, the same "the
#: real current universe, not an arbitrary subset" scope the 70-gilt pilot
#: already uses.
DEFAULT_LOOKBACK_DAYS = 3650


class TreasuryDirectSecuritiesConnector:
    dataset_code = DATASET_CODE

    def __init__(
        self, client: httpx.AsyncClient, *, security_type: str, days: int = DEFAULT_LOOKBACK_DAYS
    ) -> None:
        self._client = client
        self._security_type = security_type
        self._days = days

    async def discover(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_code=DATASET_CODE,
            description=(
                f"TreasuryDirect auctioned {self._security_type} securities "
                f"(last {self._days} days) — published by treasurydirect.gov."
            ),
        )

    async def acquire(self) -> AcquiredPayload:
        response = await fetch_auctioned_securities(
            self._client, security_type=self._security_type, days=self._days
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
        elif payload.raw_bytes.lstrip()[:1] != b"[":
            reasons.append("response body is not a JSON array")
        return CheckResult(valid=not reasons, reasons=tuple(reasons))

    def identify_schema(self, payload: AcquiredPayload) -> CheckResult:
        try:
            records = json.loads(payload.raw_bytes)
        except Exception as exc:  # noqa: BLE001 - any parse failure means QUARANTINED, not a crash
            return CheckResult(valid=False, reasons=(f"not valid JSON: {exc}",))
        if not isinstance(records, list):
            return CheckResult(valid=False, reasons=("expected a JSON array",))
        if records and "cusip" not in records[0]:
            return CheckResult(valid=False, reasons=("records missing expected 'cusip' field",))
        return CheckResult(valid=True)

    def parse(self, payload: AcquiredPayload) -> list[TreasurySecurityCandidate | RecordIssue]:
        records = json.loads(payload.raw_bytes)
        return parse_auctioned_securities(records, queried_type=self._security_type)

    def checkpoint(self, payload: AcquiredPayload) -> Checkpoint:
        records = json.loads(payload.raw_bytes)
        cusips = sorted({r["cusip"] for r in records if r.get("cusip")})
        return Checkpoint(token=cusips[-1] if cusips else "")

    async def health(self) -> bool:
        try:
            payload = await self.acquire()
        except httpx.HTTPError:
            return False
        return self.verify_transport(payload).valid
