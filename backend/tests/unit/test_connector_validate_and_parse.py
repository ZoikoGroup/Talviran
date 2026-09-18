"""validate_and_parse() (DATA-002 §7 orchestration) against the real DMO
connector: before this existed, verify_transport/identify_schema were
fully built and unit-tested in isolation, but nothing in the real
ingestion path (scripts/ingest_dev_data.py, the only real caller) ever
called them before parse() - a genuine schema-drift payload would have
reached the parser built for the old shape instead of being quarantined.
"""

import datetime as dt
from pathlib import Path

import httpx

from app.modules.market.connectors.base import AcquiredPayload, Quarantined, validate_and_parse
from app.modules.market.connectors.dmo_gilts.mapping import GiltReferenceCandidate
from app.modules.market.connectors.dmo_gilts.reference_connector import DMOGiltsReferenceConnector

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "dmo_gilts_in_issue.xml"

_connector = DMOGiltsReferenceConnector(httpx.AsyncClient())


def _payload(raw_bytes: bytes, *, content_type: str = "text/xml; charset=utf-8") -> AcquiredPayload:
    return AcquiredPayload(
        raw_bytes=raw_bytes, content_type=content_type, status_code=200,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="https://www.dmo.gov.uk/data/xmldatareport?reportCode=D1A",
    )


def test_valid_payload_parses_through_to_real_candidates() -> None:
    result = validate_and_parse(_connector, _payload(FIXTURE_PATH.read_bytes()))

    assert not isinstance(result, Quarantined)
    assert any(isinstance(c, GiltReferenceCandidate) for c in result)


def test_a_bot_check_html_page_is_quarantined_not_parsed() -> None:
    # The exact real-world failure mode this exists for (client.py's own
    # docstring: live DMO access is bot-blocked) - a 200 OK with an HTML
    # bot-check page instead of the expected XML feed.
    bot_check_html = b"<html><head><title>302 Found</title></head></html>"

    result = validate_and_parse(_connector, _payload(bot_check_html, content_type="text/html"))

    assert isinstance(result, Quarantined)
    assert result.reasons != ()


def test_garbage_bytes_are_quarantined_not_parsed() -> None:
    result = validate_and_parse(_connector, _payload(b"not xml at all {{{"))

    assert isinstance(result, Quarantined)


def test_unexpected_status_code_is_quarantined_before_schema_is_even_checked() -> None:
    payload = AcquiredPayload(
        raw_bytes=FIXTURE_PATH.read_bytes(),  # otherwise perfectly valid XML
        content_type="text/xml; charset=utf-8",
        status_code=503,
        fetched_at=dt.datetime.now(dt.UTC),
        source_url="https://www.dmo.gov.uk/data/xmldatareport?reportCode=D1A",
    )

    result = validate_and_parse(_connector, payload)

    assert isinstance(result, Quarantined)
    assert any("503" in reason for reason in result.reasons)
