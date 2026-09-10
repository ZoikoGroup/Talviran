"""No-DB unit tests for the parts of the rights engine that must fail closed
before ever touching the database.
"""

from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rights.engine import RightsDecision, evaluate_action


class _PoisonedSession:
    """Raises on any DB access — proves the None short-circuit genuinely
    never reaches the database rather than happening to return DENY anyway.
    """

    async def get(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("must not query the DB when rights_profile_id is None")

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("must not query the DB when rights_profile_id is None")


async def test_none_profile_id_denies_without_touching_db() -> None:
    session = cast(AsyncSession, _PoisonedSession())
    decision = await evaluate_action(session, "retrieve", None)
    assert decision is RightsDecision.DENY
