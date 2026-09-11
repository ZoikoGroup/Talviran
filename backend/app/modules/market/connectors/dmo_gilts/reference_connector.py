"""The first real connector: UK DMO's Gilts in Issue feed (report D1A).

Deliberately does NOT resolve identity or write source_observation rows —
that's identity-resolve + observation-write, P1 week 9's job (DATA-002's
own pipeline ordering: acquire -> manifest -> validate -> normalise ->
identity-resolve -> observation-write -> reconcile -> publish). This
connector only covers acquire through normalise.

See client.py's docstring for why xmldatareport is used instead of
ExportReport/pdfdatareport, and for the caveat that live automated access
to even this endpoint is unconfirmed.
"""

import httpx
from defusedxml import ElementTree as safe_ET  # type: ignore[import-untyped]

from app.modules.market.connectors.base import (
    AcquiredPayload,
    Checkpoint,
    CheckResult,
    DatasetDescriptor,
)
from app.modules.market.connectors.dmo_gilts.client import fetch_gilts_in_issue, now_utc
from app.modules.market.connectors.dmo_gilts.mapping import (
    GiltReferenceCandidate,
    RecordIssue,
    normalise_record,
)

DATASET_CODE = "uk-dmo.gilts-in-issue"
_EXPECTED_ROOT_TAG = "Data"
_EXPECTED_RECORD_TAG = "View_GILTS_IN_ISSUE"


class DMOGiltsReferenceConnector:
    dataset_code = DATASET_CODE

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def discover(self) -> DatasetDescriptor:
        return DatasetDescriptor(
            dataset_code=DATASET_CODE,
            description=(
                "UK DMO Gilts in Issue (report D1A) — reference terms for "
                "every gilt currently in issue."
            ),
        )

    async def acquire(self) -> AcquiredPayload:
        response = await fetch_gilts_in_issue(self._client)
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
        looks_like_xml = payload.raw_bytes[:1] == b"<"
        if "xml" not in payload.content_type.lower() and not looks_like_xml:
            reasons.append(f"unexpected content-type: {payload.content_type!r}")
        return CheckResult(valid=not reasons, reasons=tuple(reasons))

    def identify_schema(self, payload: AcquiredPayload) -> CheckResult:
        try:
            root = safe_ET.fromstring(payload.raw_bytes)
        except Exception as exc:  # noqa: BLE001 - any parse failure means QUARANTINED, not a crash
            return CheckResult(valid=False, reasons=(f"not well-formed XML: {exc}",))

        if root.tag != _EXPECTED_ROOT_TAG:
            return CheckResult(valid=False, reasons=(f"unexpected root element: {root.tag!r}",))

        if not root.findall(_EXPECTED_RECORD_TAG):
            return CheckResult(valid=False, reasons=(f"no {_EXPECTED_RECORD_TAG} elements found",))

        return CheckResult(valid=True)

    def parse(self, payload: AcquiredPayload) -> list[GiltReferenceCandidate | RecordIssue]:
        root = safe_ET.fromstring(payload.raw_bytes)
        results: list[GiltReferenceCandidate | RecordIssue] = []
        for element in root.findall(_EXPECTED_RECORD_TAG):
            attrs: dict[str, str] = dict(element.attrib)
            results.append(normalise_record(attrs))
        return results

    def checkpoint(self, payload: AcquiredPayload) -> Checkpoint:
        try:
            root = safe_ET.fromstring(payload.raw_bytes)
            first = root.find(_EXPECTED_RECORD_TAG)
            token = first.get("CLOSE_OF_BUSINESS_DATE", "") if first is not None else ""
        except Exception:  # noqa: BLE001 - a bad payload just means "no checkpoint", not a crash
            token = ""
        return Checkpoint(token=token)

    async def health(self) -> bool:
        try:
            payload = await self.acquire()
        except httpx.HTTPError:
            return False
        return self.verify_transport(payload).valid
