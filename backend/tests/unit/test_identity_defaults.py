"""New accounts must start free, not on a paid plan by schema default."""

from app.modules.identity.models import Account


def test_new_account_schema_defaults_to_free_explorer_tier() -> None:
    """Omitting plan_tier at signup must never grant paid Professional access.

    Both the ORM-side and the DB-side default are asserted: signup inserts
    through the ORM, but other writers (migrations, SQL scripts, future
    services) can omit the column entirely and rely on the server default.
    """
    plan_tier = Account.__table__.c.plan_tier
    assert plan_tier.default is not None
    assert plan_tier.default.arg == "explorer"
    assert plan_tier.server_default is not None
    assert plan_tier.server_default.arg == "explorer"

    cadence = Account.__table__.c.billing_cadence
    assert cadence.default is not None
    assert cadence.default.arg == "monthly"
    assert cadence.server_default is not None
    assert cadence.server_default.arg == "monthly"
