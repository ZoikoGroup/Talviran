from app.modules.market.pipeline.reconciliation_policy import (
    CONFLICT_ACTION_FLAG,
    DEFAULT_POLICIES,
    GILT_REFERENCE_TERMS_POLICY,
)


def test_gilt_reference_terms_policy_requires_exact_match() -> None:
    # Reference terms (coupon, maturity) must match exactly across sources
    # — no tolerance makes sense for a fact that either is or isn't the
    # instrument's actual coupon.
    assert GILT_REFERENCE_TERMS_POLICY.tolerance is None
    assert GILT_REFERENCE_TERMS_POLICY.conflict_action == CONFLICT_ACTION_FLAG


def test_default_policies_registers_gilt_reference_terms() -> None:
    assert DEFAULT_POLICIES["GILT_REFERENCE_TERMS"] is GILT_REFERENCE_TERMS_POLICY
