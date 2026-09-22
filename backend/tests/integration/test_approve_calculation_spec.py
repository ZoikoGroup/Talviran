"""Proves scripts.approve_calculation_spec.approve()'s governance logic:
this is the ONLY path that may flip a spec DRAFT -> APPROVED, and it must
refuse in every case except "a registered spec, currently DRAFT, whose
golden-test module fully passes".
"""

import uuid
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest as pytest_module
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import db as core_db
from app.core.config import get_settings
from app.modules.calculation.models import (
    STATUS_APPROVED,
    STATUS_DEPRECATED,
    STATUS_DRAFT,
    CalculationSpecification,
)
from scripts.approve_calculation_spec import approve


@pytest_asyncio.fixture(autouse=True)
async def _fresh_process_engine_per_test() -> AsyncIterator[None]:
    # approve() calls app.core.db.get_session_factory() directly (it's a
    # real CLI script, meant to run with the app's one persistent engine) -
    # but that engine is a process-level singleton bound to whatever event
    # loop first created it, and pytest-asyncio gives each test its own loop
    # (the same lesson conftest.py's db_session fixture exists for). Reset
    # the singleton around each test so approve()'s internal engine is
    # created fresh in THIS test's loop, not reused from a torn-down one.
    #
    # get_engine() reads settings.database_url (the dev database), but this
    # test's own db_session fixture points at test_database_url - the
    # separate talvrin_test database. Without this swap, _seed_spec's row
    # (written via db_session) and approve()'s own lookup (via
    # get_session_factory()) would silently be looking at two different
    # databases - exactly the class of bug the test-database split was
    # built to prevent elsewhere, just relocated to this one script's
    # direct get_session_factory() usage.
    settings = get_settings()
    original_database_url = settings.database_url
    settings.database_url = settings.test_database_url
    core_db._engine = None
    core_db._session_factory = None
    yield
    if core_db._engine is not None:
        await core_db._engine.dispose()
    core_db._engine = None
    core_db._session_factory = None
    settings.database_url = original_database_url


async def _seed_spec(session: AsyncSession, *, status: str) -> str:
    code = f"test-spec-{uuid.uuid4().hex[:8]}"
    session.add(
        CalculationSpecification(code=code, version="1", status=status, description="test")
    )
    await session.commit()
    return code


async def test_unknown_code_is_refused(db_session: AsyncSession) -> None:
    exit_code = await approve("no-such-spec-code")
    assert exit_code == 1


async def test_missing_specification_row_is_refused(db_session: AsyncSession) -> None:
    with patch.dict(
        "scripts.approve_calculation_spec._GOLDEN_TEST_PATHS",
        {"unregistered-in-db": "tests/golden/test_gilt_price_yield_v1_golden.py"},
    ):
        exit_code = await approve("unregistered-in-db")
    assert exit_code == 1


async def test_already_approved_is_a_no_op(db_session: AsyncSession) -> None:
    code = await _seed_spec(db_session, status=STATUS_APPROVED)
    with patch.dict(
        "scripts.approve_calculation_spec._GOLDEN_TEST_PATHS",
        {code: "tests/golden/test_gilt_price_yield_v1_golden.py"},
    ):
        exit_code = await approve(code)
    assert exit_code == 0


async def test_deprecated_spec_is_refused_not_reapproved(db_session: AsyncSession) -> None:
    code = await _seed_spec(db_session, status=STATUS_DEPRECATED)
    with patch.dict(
        "scripts.approve_calculation_spec._GOLDEN_TEST_PATHS",
        {code: "tests/golden/test_gilt_price_yield_v1_golden.py"},
    ):
        exit_code = await approve(code)
    assert exit_code == 1

    row = (
        await db_session.execute(
            CalculationSpecification.__table__.select().where(
                CalculationSpecification.code == code
            )
        )
    ).mappings().one()
    assert row["status"] == STATUS_DEPRECATED, "must not silently un-deprecate"


async def test_draft_spec_that_fails_the_gate_stays_draft(db_session: AsyncSession) -> None:
    code = await _seed_spec(db_session, status=STATUS_DRAFT)
    with (
        patch.dict(
            "scripts.approve_calculation_spec._GOLDEN_TEST_PATHS",
            {code: "tests/golden/test_gilt_price_yield_v1_golden.py"},
        ),
        patch(
            "scripts.approve_calculation_spec.pytest.main",
            return_value=pytest_module.ExitCode.TESTS_FAILED,
        ),
    ):
        exit_code = await approve(code)
    assert exit_code == 1

    row = (
        await db_session.execute(
            CalculationSpecification.__table__.select().where(
                CalculationSpecification.code == code
            )
        )
    ).mappings().one()
    assert row["status"] == STATUS_DRAFT, "a failed gate must never approve"


async def test_draft_spec_that_passes_the_gate_is_approved(db_session: AsyncSession) -> None:
    code = await _seed_spec(db_session, status=STATUS_DRAFT)
    with patch.dict(
        "scripts.approve_calculation_spec._GOLDEN_TEST_PATHS",
        {code: "tests/golden/test_gilt_price_from_curve_v1_golden.py"},
    ):
        exit_code = await approve(code)
    assert exit_code == 0

    row = (
        await db_session.execute(
            CalculationSpecification.__table__.select().where(
                CalculationSpecification.code == code
            )
        )
    ).mappings().one()
    assert row["status"] == STATUS_APPROVED
