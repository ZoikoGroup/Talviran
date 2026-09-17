"""compute_freshness() against DATA-002's five-state model (minus
SUSPENDED, which needs monitoring coverage tracking that doesn't exist
yet) - the fix for evidence citations that used to hardcode "CURRENT"
regardless of how old the underlying accepted_fact actually was.
"""

import datetime as dt

import pytest

from app.modules.market.freshness import (
    STATE_CURRENT,
    STATE_DELAYED,
    STATE_STALE,
    STATE_UNAVAILABLE,
    FreshnessProfile,
    compute_freshness,
)

_NOW = dt.datetime(2026, 9, 17, 12, 0, tzinfo=dt.UTC)

_PROFILE = FreshnessProfile(
    metric_id="TEST_METRIC",
    freshness_slo=dt.timedelta(hours=1),
    delayed_after=dt.timedelta(hours=3),
    stale_after=dt.timedelta(hours=6),
    unavailable_after=dt.timedelta(hours=12),
)


@pytest.fixture(autouse=True)
def _register_test_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.market.freshness as freshness_module

    monkeypatch.setitem(freshness_module.DEFAULT_PROFILES, _PROFILE.metric_id, _PROFILE)


def _age_ago(hours: float) -> dt.datetime:
    return _NOW - dt.timedelta(hours=hours)


def test_within_slo_is_current() -> None:
    assert (
        compute_freshness(metric_id="TEST_METRIC", knowledge_time=_age_ago(0.5), now=_NOW)
        == STATE_CURRENT
    )


def test_exactly_at_slo_boundary_is_still_current() -> None:
    assert (
        compute_freshness(metric_id="TEST_METRIC", knowledge_time=_age_ago(1), now=_NOW)
        == STATE_CURRENT
    )


def test_beyond_slo_within_delay_tolerance_is_delayed() -> None:
    assert (
        compute_freshness(metric_id="TEST_METRIC", knowledge_time=_age_ago(2), now=_NOW)
        == STATE_DELAYED
    )


def test_beyond_delay_tolerance_within_stale_threshold_is_stale() -> None:
    assert (
        compute_freshness(metric_id="TEST_METRIC", knowledge_time=_age_ago(5), now=_NOW)
        == STATE_STALE
    )


def test_beyond_stale_threshold_but_within_unavailable_after_is_still_stale() -> None:
    assert (
        compute_freshness(metric_id="TEST_METRIC", knowledge_time=_age_ago(10), now=_NOW)
        == STATE_STALE
    )


def test_beyond_unavailable_after_is_unavailable() -> None:
    assert (
        compute_freshness(metric_id="TEST_METRIC", knowledge_time=_age_ago(13), now=_NOW)
        == STATE_UNAVAILABLE
    )


def test_no_unavailable_after_configured_means_stale_persists_indefinitely() -> None:
    profile = FreshnessProfile(
        metric_id="NO_CUTOFF_METRIC",
        freshness_slo=dt.timedelta(hours=1),
        delayed_after=dt.timedelta(hours=2),
        stale_after=dt.timedelta(hours=3),
        unavailable_after=None,
    )
    import app.modules.market.freshness as freshness_module

    freshness_module.DEFAULT_PROFILES[profile.metric_id] = profile
    try:
        assert (
            compute_freshness(
                metric_id="NO_CUTOFF_METRIC",
                knowledge_time=_age_ago(24 * 365),  # a year old
                now=_NOW,
            )
            == STATE_STALE
        )
    finally:
        del freshness_module.DEFAULT_PROFILES[profile.metric_id]


def test_unregistered_metric_raises_rather_than_defaulting_to_current() -> None:
    with pytest.raises(KeyError, match="no FreshnessProfile registered"):
        compute_freshness(metric_id="NO_SUCH_METRIC", knowledge_time=_NOW, now=_NOW)


def test_registered_production_metrics_all_resolve() -> None:
    from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
    from app.modules.market.pipeline.curve_ingest import METRIC_UK_GILT_NOMINAL_SPOT_CURVE
    from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS

    for metric_id in (
        METRIC_GILT_REFERENCE_TERMS,
        METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
        METRIC_MODEL_IMPLIED_CLEAN_PRICE,
    ):
        assert compute_freshness(metric_id=metric_id, knowledge_time=_NOW, now=_NOW) == (
            STATE_CURRENT
        )
