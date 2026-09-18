"""One DBnomics macro/economic series connector.

Deliberately does NOT derive a subject_id, resolve identity, or write
source_observation rows — that's app.modules.market.pipeline.macro_ingest's
job, downstream of this connector, following the same acquire -> manifest
-> validate -> normalise -> observation-write -> reconcile -> publish
ordering as the existing gilt, curve and FX connectors.

One instance tracks exactly one (provider, dataset, series) triple —
covering more series (e.g. GDP for several countries) means more
instances, the same reasoning the Frankfurter connector uses for covering
several currency pairs.
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
from app.modules.market.connectors.dbnomics_macro.client import fetch_series, now_utc
from app.modules.market.connectors.dbnomics_macro.mapping import (
    MacroObservationCandidate,
    RecordIssue,
    parse_series_response,
)

DATASET_CODE = "dbnomics.series"


class DBnomicsMacroConnector:
    dataset_code = DATASET_CODE

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        provider_code: str,
        dataset_code: str,
        series_code: str,
    ) -> None:
        self._client = client
        self._provider_code = provider_code
        self._dataset_code = dataset_code
        self._series_code = series_code

    async def discover(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_code=DATASET_CODE,
            description=(
                f"DBnomics series {self._provider_code}/{self._dataset_code}/"
                f"{self._series_code}, aggregated from official statistical sources."
            ),
        )

    async def acquire(self) -> AcquiredPayload:
        response = await fetch_series(
            self._client,
            provider_code=self._provider_code,
            dataset_code=self._dataset_code,
            series_code=self._series_code,
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

        if not isinstance(body, dict) or "series" not in body:
            return CheckResult(valid=False, reasons=("response has no top-level 'series' key",))

        candidates = parse_series_response(body)
        if not any(isinstance(c, MacroObservationCandidate) for c in candidates):
            reasons = tuple(c.reason for c in candidates if isinstance(c, RecordIssue))
            return CheckResult(
                valid=False, reasons=reasons or ("no observations parsed from response",)
            )
        return CheckResult(valid=True)

    def parse(self, payload: AcquiredPayload) -> list[MacroObservationCandidate | RecordIssue]:
        return parse_series_response(self._decode(payload))

    def checkpoint(self, payload: AcquiredPayload) -> Checkpoint:
        candidates = self.parse(payload)
        periods = sorted(
            {c.period_start_day for c in candidates if isinstance(c, MacroObservationCandidate)}
        )
        token = periods[-1].isoformat() if periods else ""
        return Checkpoint(token=token)

    async def health(self) -> bool:
        try:
            payload = await self.acquire()
        except httpx.HTTPError:
            return False
        return self.verify_transport(payload).valid
