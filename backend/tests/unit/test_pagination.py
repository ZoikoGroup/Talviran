import uuid

import pytest

from app.core.pagination import InvalidCursorError, decode_cursor, encode_cursor


def test_cursor_round_trips() -> None:
    original = uuid.uuid4()
    assert decode_cursor(encode_cursor(original)) == original


def test_invalid_cursor_raises_typed_error() -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor("not-a-valid-cursor")
