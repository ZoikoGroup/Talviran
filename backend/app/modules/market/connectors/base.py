"""The Connector Protocol (DATA-002 §3.1) — every market data source
implements this shape: discover / acquire / verify_transport /
identify_schema / parse / checkpoint / health. A connector is explicitly
forbidden from choosing truth, fuzzy-matching identity, calling AI, or
writing accepted_fact/calculation_result — it only acquires, validates and
normalises. Identity resolution, reconciliation and truth publication are
app.modules.market.pipeline's job (P1 week 9), not the connector's.

A structural Protocol, not an ABC — connectors don't need to inherit from
anything, just implement the same method shapes DATA-002 names.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DatasetDescriptor:
    dataset_code: str
    description: str


@dataclass(frozen=True)
class AcquiredPayload:
    raw_bytes: bytes
    content_type: str
    status_code: int
    fetched_at: dt.datetime
    source_url: str


@dataclass(frozen=True)
class CheckResult:
    valid: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Checkpoint:
    """Opaque to callers — connector-specific. Lets a caller detect "the
    source hasn't actually published anything new since we last looked"
    without re-parsing the full payload.
    """

    token: str


class Connector(Protocol):
    dataset_code: str

    async def discover(self) -> DatasetDescriptor: ...

    async def acquire(self) -> AcquiredPayload: ...

    def verify_transport(self, payload: AcquiredPayload) -> CheckResult: ...

    def identify_schema(self, payload: AcquiredPayload) -> CheckResult: ...

    def parse(self, payload: AcquiredPayload) -> list[object]: ...

    def checkpoint(self, payload: AcquiredPayload) -> Checkpoint: ...

    async def health(self) -> bool: ...
