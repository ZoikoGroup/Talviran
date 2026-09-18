"""Parsing/normalisation for DBnomics' /series response — isolated from
the connector so "how do we read this specific shape" is unit-testable
without any network dependency.

Verified live against the real API (2026-09-18): a successful response's
series.docs[0] carries three PARALLEL arrays — period (e.g. "2023"),
period_start_day (e.g. "2023-01-01" — DBnomics' own pre-computed ISO
date, so this never has to hand-parse annual/quarterly/monthly period
strings itself), and value — plus an @frequency field (e.g. "annual").

Only "annual" is supported today (both pilot series — GDP and CPI — are
annual): a period's span (needed to build a valid_range) is derived from
@frequency, and an unsupported frequency produces a RecordIssue for the
whole series rather than silently guessing a span. A future
quarterly/monthly series is a real, explicit extension here, not a
same-day addition.

Never coerces or guesses (DATA-002): a missing/malformed series.docs
entry, a length mismatch between the three parallel arrays, or a
null/non-numeric value produces a RecordIssue rather than a fabricated
value or a crash that drops every other observation.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

SUPPORTED_FREQUENCY = "annual"


@dataclass(frozen=True)
class MacroObservationCandidate:
    provider_code: str
    dataset_code: str
    series_code: str
    period: str
    period_start_day: dt.date
    period_end_day: dt.date  # exclusive — the day after the period actually ends
    value: Decimal


@dataclass(frozen=True)
class RecordIssue:
    raw_period: str | None
    reason: str


def _add_years(d: dt.date, years: int) -> dt.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # Feb 29 landing on a non-leap target year — falling back a day is
        # the unsurprising choice; a helper shouldn't assume its own
        # inputs are always Jan-1 just because today's two pilot series are.
        return d.replace(month=2, day=28, year=d.year + years)


def parse_series_response(payload: Any) -> list["MacroObservationCandidate | RecordIssue"]:
    docs = None
    if isinstance(payload, dict):
        series = payload.get("series")
        docs = series.get("docs") if isinstance(series, dict) else None
    if not isinstance(docs, list) or not docs:
        return [RecordIssue(raw_period=None, reason="no series.docs found in response")]

    doc = docs[0]
    if not isinstance(doc, dict):
        return [RecordIssue(raw_period=None, reason="series.docs[0] is not an object")]

    frequency = doc.get("@frequency")
    if frequency != SUPPORTED_FREQUENCY:
        return [
            RecordIssue(
                raw_period=None,
                reason=(
                    f"unsupported frequency {frequency!r} "
                    f"(only {SUPPORTED_FREQUENCY!r} is handled)"
                ),
            )
        ]

    provider_code = doc.get("provider_code")
    dataset_code = doc.get("dataset_code")
    series_code = doc.get("series_code")
    periods = doc.get("period")
    starts = doc.get("period_start_day")
    values = doc.get("value")

    if not (isinstance(periods, list) and isinstance(starts, list) and isinstance(values, list)):
        return [
            RecordIssue(
                raw_period=None, reason="period/period_start_day/value is not an array"
            )
        ]

    if not (len(periods) == len(starts) == len(values)):
        return [
            RecordIssue(
                raw_period=None,
                reason=(
                    f"parallel array length mismatch: period={len(periods)}, "
                    f"period_start_day={len(starts)}, value={len(values)}"
                ),
            )
        ]

    if not (provider_code and dataset_code and series_code):
        return [
            RecordIssue(
                raw_period=None,
                reason="missing provider_code/dataset_code/series_code on series.docs[0]",
            )
        ]

    results: list[MacroObservationCandidate | RecordIssue] = []
    for period, start_str, raw_value in zip(periods, starts, values, strict=True):
        if raw_value is None:
            results.append(RecordIssue(raw_period=str(period), reason="null value"))
            continue
        if not isinstance(raw_value, int | float):
            results.append(
                RecordIssue(raw_period=str(period), reason=f"non-numeric value: {raw_value!r}")
            )
            continue
        try:
            value = Decimal(str(raw_value))
        except InvalidOperation:
            results.append(
                RecordIssue(raw_period=str(period), reason=f"unparseable value: {raw_value!r}")
            )
            continue

        try:
            start_date = dt.date.fromisoformat(start_str)
        except (TypeError, ValueError):
            results.append(
                RecordIssue(
                    raw_period=str(period),
                    reason=f"unparseable period_start_day: {start_str!r}",
                )
            )
            continue

        results.append(
            MacroObservationCandidate(
                provider_code=str(provider_code),
                dataset_code=str(dataset_code),
                series_code=str(series_code),
                period=str(period),
                period_start_day=start_date,
                period_end_day=_add_years(start_date, 1),
                value=value,
            )
        )

    return results
