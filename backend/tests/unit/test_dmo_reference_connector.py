"""Connector-level tests against the real captured DMO fixture — proves
verify_transport/identify_schema/parse work on genuine DMO output, without
requiring a live network call (which, per client.py's docstring, isn't
confirmed to work for an automated client at all).
"""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import httpx

from app.modules.market.connectors.base import AcquiredPayload
from app.modules.market.connectors.dmo_gilts.mapping import GILT_TYPE_INDEX_LINKED, RecordIssue
from app.modules.market.connectors.dmo_gilts.reference_connector import DMOGiltsReferenceConnector

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "dmo_gilts_in_issue.xml"

# httpx.AsyncClient is never actually used by these tests (no acquire()
# call), but the constructor requires one — a throwaway instance is enough.

_connector = DMOGiltsReferenceConnector(httpx.AsyncClient())


def _real_payload() -> AcquiredPayload:
    return AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),
        content_type="text/xml; charset=utf-8",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="https://www.dmo.gov.uk/data/xmldatareport?reportCode=D1A",
    )


def test_verify_transport_valid_for_real_fixture() -> None:
    result = _connector.verify_transport(_real_payload())
    assert result.valid is True
    assert result.reasons == ()


def test_verify_transport_invalid_for_non_200() -> None:
    payload = AcquiredPayload(
        raw_bytes=b"<Data></Data>",
        content_type="text/xml",
        status_code=503,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="https://www.dmo.gov.uk/data/xmldatareport?reportCode=D1A",
    )
    result = _connector.verify_transport(payload)
    assert result.valid is False
    assert any("503" in reason for reason in result.reasons)


def test_verify_transport_invalid_for_empty_body() -> None:
    payload = AcquiredPayload(
        raw_bytes=b"",
        content_type="text/xml",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="https://www.dmo.gov.uk/data/xmldatareport?reportCode=D1A",
    )
    result = _connector.verify_transport(payload)
    assert result.valid is False


def test_identify_schema_valid_for_real_fixture() -> None:
    result = _connector.identify_schema(_real_payload())
    assert result.valid is True


def test_identify_schema_invalid_for_the_bot_check_html_page() -> None:
    # This is exactly what a live acquire() would get today (see client.py)
    # — the connector must quarantine it, not crash or silently treat it as
    # an empty dataset.
    bot_check_html = b"<html><head><title>302 Found</title></head></html>"
    payload = AcquiredPayload(
        raw_bytes=bot_check_html,
        content_type="text/html",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="https://www.dmo.gov.uk/data/xmldatareport?reportCode=D1A",
    )
    result = _connector.identify_schema(payload)
    assert result.valid is False


def test_identify_schema_invalid_for_garbage_bytes() -> None:
    payload = AcquiredPayload(
        raw_bytes=b"not xml at all {{{",
        content_type="text/xml",
        status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="https://www.dmo.gov.uk/data/xmldatareport?reportCode=D1A",
    )
    result = _connector.identify_schema(payload)
    assert result.valid is False


def test_parse_finds_seed_gilt_with_correct_terms() -> None:
    candidates = _connector.parse(_real_payload())

    matches = [
        c
        for c in candidates
        if not isinstance(c, RecordIssue) and c.isin == "GB0032452392"
    ]
    assert len(matches) == 1
    seed = matches[0]
    assert seed.instrument_name == "4¼% Treasury Stock 2036"
    assert seed.coupon_rate == Decimal("4.25")
    assert seed.redemption_date == dt.date(2036, 3, 7)
    assert seed.first_issue_date == dt.date(2003, 2, 27)


def test_parse_distinguishes_index_linked_records() -> None:
    candidates = _connector.parse(_real_payload())

    matches = [
        c
        for c in candidates
        if not isinstance(c, RecordIssue) and c.isin == "GB00BDX8CX86"
    ]
    assert len(matches) == 1
    assert matches[0].gilt_type == GILT_TYPE_INDEX_LINKED
    # Confirms this ISIN is genuinely NOT the 2036 4.25% gilt (the bug
    # found and fixed in frontend/src/data/mockReply.ts).
    assert "2068" in matches[0].instrument_name


def test_parse_produces_no_record_issues_for_the_real_fixture() -> None:
    # Every real record in the fixture has all required attributes — if
    # this ever fails, DMO's format changed in a way worth knowing about.
    candidates = _connector.parse(_real_payload())
    issues = [c for c in candidates if isinstance(c, RecordIssue)]
    assert issues == []
    assert len(candidates) > 100  # sanity: the fixture has 104 real records


def test_checkpoint_returns_close_of_business_date() -> None:
    checkpoint = _connector.checkpoint(_real_payload())
    assert checkpoint.token == "2026-09-10T00:00:00"
