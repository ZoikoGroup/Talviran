"""FIN-001's dual-implementation + golden-test gate, made real: this is the
ONLY sanctioned way a calculation_specification moves from DRAFT to
APPROVED — never a runtime code path, never something an app request can
trigger (calculation/models.py: "status... is a record of that decision,
not something the app can set unilaterally at compute time").

Run with:

    uv run python -m scripts.approve_calculation_spec gilt_price_yield_v1

Runs that spec's golden-test module in-process (production implementation
vs DMO's own worked examples, shadow implementation vs the same examples,
production vs shadow agreement, plus the corpus-integrity check) and only
writes APPROVED if every test in it passes. A DEPRECATED spec is refused,
not silently re-approved - that requires a separate, explicit decision this
script does not make.
"""

import argparse
import asyncio
import sys

import pytest
from sqlalchemy import select

from app.core.db import get_session_factory
from app.modules.calculation.models import (
    STATUS_APPROVED,
    STATUS_DEPRECATED,
    STATUS_DRAFT,
    CalculationSpecification,
)

_GOLDEN_TEST_PATHS: dict[str, str] = {
    "gilt_price_yield_v1": "tests/golden/test_gilt_price_yield_v1_golden.py",
    "gilt_price_from_curve_v1": "tests/golden/test_gilt_price_from_curve_v1_golden.py",
}


async def approve(code: str) -> int:
    if code not in _GOLDEN_TEST_PATHS:
        print(f"No golden-test module registered for {code!r}. Known specs: "
              f"{sorted(_GOLDEN_TEST_PATHS)}")
        return 1

    factory = get_session_factory()
    async with factory() as session:
        spec = (
            await session.execute(
                select(CalculationSpecification).where(CalculationSpecification.code == code)
            )
        ).scalar_one_or_none()
        if spec is None:
            print(f"No calculation_specification row for code {code!r} - seed it first.")
            return 1

        if spec.status == STATUS_APPROVED:
            print(f"{code} v{spec.version} is already APPROVED.")
            return 0
        if spec.status == STATUS_DEPRECATED:
            print(
                f"{code} v{spec.version} is DEPRECATED - re-approving a deprecated spec is "
                "a separate, explicit decision this script does not make."
            )
            return 1

        assert spec.status == STATUS_DRAFT

        print(f"Running golden-test gate for {code} v{spec.version}...")
        exit_code = pytest.main([_GOLDEN_TEST_PATHS[code], "-q"])

        if exit_code != pytest.ExitCode.OK:
            print(
                f"\nGolden-test gate FAILED for {code} - status remains DRAFT. "
                "Not approved."
            )
            return 1

        spec.status = STATUS_APPROVED
        await session.commit()
        print(f"\nGolden-test gate passed. {code} v{spec.version} -> APPROVED.")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code", help="calculation_specification.code to approve")
    args = parser.parse_args()
    sys.exit(asyncio.run(approve(args.code)))


if __name__ == "__main__":
    main()
