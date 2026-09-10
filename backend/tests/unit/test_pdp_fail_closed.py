"""Proves the PDP's outer fail-closed wrapper: any exception during
evaluation (simulating a DB outage/timeout, or any bug in a check) must
resolve to DENY, and the DENY verdict must still get logged — never let an
exception escape as an implicit permit, and never lose the audit trail of
why a request was denied.
"""

from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.policy.pdp import Decision, PolicyContext, evaluate


class _TimingOutSession:
    """execute() always raises, simulating a PDP backend timeout. add() is a
    no-op sink so _log_decision can still record the resulting DENY without
    needing a real database.
    """

    def __init__(self) -> None:
        self.added: list[object] = []

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        raise TimeoutError("simulated PDP backend timeout")

    def add(self, obj: object) -> None:
        self.added.append(obj)


async def test_pdp_denies_on_backend_timeout_and_still_logs() -> None:
    ctx = PolicyContext(
        principal_id=None,
        account_id=None,
        jurisdiction_code="GB",
        capability_code="research.gilt_facts",
    )
    session = cast(AsyncSession, _TimingOutSession())

    decision = await evaluate(session, ctx)

    assert isinstance(decision, Decision)
    assert decision.is_permit is False
    assert decision.reason_codes == ["PDP_EVALUATION_ERROR"]
    # The DENY verdict was still added to the session for the caller to
    # commit — a backend failure must not also erase the audit trail.
    assert len(cast(_TimingOutSession, session).added) == 1
