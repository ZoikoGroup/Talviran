"""Runs P2's calculation_supersession rerun flow for a real methodology
version bump: given a previously-used spec code and a newly APPROVED spec
code, recomputes every (subject, as_of_date) pair that has a result under
the old code, producing new ACTIVE rows under the new code alongside the
old ones (never superseding them - see
app/modules/calculation/pipeline/rerun.py's docstring for why).

Run with:

    uv run python -m scripts.rerun_calculation_spec_version \\
        --previous-code gilt_price_from_curve_v1 \\
        --new-code gilt_price_from_curve_v2
"""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.calculation.models import CalculationSpecification
from app.modules.calculation.pipeline.rerun import (
    RerunRefused,
    rerun_for_new_specification_version,
)


async def _spec_for_code(session: AsyncSession, code: str) -> CalculationSpecification | None:
    return (
        await session.execute(
            select(CalculationSpecification).where(CalculationSpecification.code == code)
        )
    ).scalar_one_or_none()


async def rerun(previous_code: str, new_code: str) -> int:
    factory = get_session_factory()
    async with factory() as session:
        previous_spec = await _spec_for_code(session, previous_code)
        if previous_spec is None:
            print(f"No calculation_specification row for code {previous_code!r}.")
            return 1

        new_spec = await _spec_for_code(session, new_code)
        if new_spec is None:
            print(
                f"No calculation_specification row for code {new_code!r} - "
                "seed and approve it first."
            )
            return 1

        outcome = await rerun_for_new_specification_version(
            session,
            previous_specification_id=previous_spec.id,
            new_specification_id=new_spec.id,
        )
        if isinstance(outcome, RerunRefused):
            print(f"Refused: {outcome.reason}")
            return 1

        await session.commit()

        accepted = sum(1 for o in outcome if type(o.result).__name__ == "ModelImpliedPriceComputed")
        skipped = len(outcome) - accepted
        print(
            f"Rerun complete: {len(outcome)} (subject, as_of_date) pair(s) processed under "
            f"{new_code} ({accepted} computed, {skipped} skipped)."
        )
        for o in outcome:
            print(f"  {o.subject_id} @ {o.as_of_date}: {o.result}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-code", required=True, help="the spec code being replaced")
    parser.add_argument("--new-code", required=True, help="the newly APPROVED spec code")
    args = parser.parse_args()
    sys.exit(asyncio.run(rerun(args.previous_code, args.new_code)))


if __name__ == "__main__":
    main()
