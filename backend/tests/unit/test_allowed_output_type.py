"""Pins the closed output-type enum — the regression test that blocks
"just add REC.BUY_SELL_HOLD, we'll filter it later." Any change to this
test must be a deliberate ADR-backed decision, not a routine PR diff.
"""

from app.modules.policy.allowed_output_type import AllowedOutputType


def test_exactly_eight_output_types() -> None:
    assert len(AllowedOutputType) == 8


def test_output_type_members_match_pol_001() -> None:
    assert {member.value for member in AllowedOutputType} == {
        "FACTUAL_EVIDENCE",
        "CALCULATION_RESULT",
        "USER_DIRECTED_COMPARISON",
        "DOCUMENT_EXPLANATION",
        "OBJECTIVE_EVENT",
        "USER_RULE_ALERT",
        "SOURCE_DISCOVERY",
        "NEUTRAL_EDUCATION",
    }


def test_no_recommendation_shaped_member_exists() -> None:
    forbidden_fragments = ("BUY", "SELL", "HOLD", "TARGET_PRICE", "TOP_PICK", "SUITABIL", "RATING")
    for member in AllowedOutputType:
        for fragment in forbidden_fragments:
            assert fragment not in member.value, (
                f"{member.value} looks recommendation-shaped — this must never happen"
            )
