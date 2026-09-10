"""The closed set of response shapes Talvrin is structurally capable of
producing (POL-001). This is the primary recommendation-safety control, not
a content filter bolted on after generation: there is no BUY_SELL_HOLD,
TARGET_PRICE, TOP_PICK, or SUITABILITY member here, ever, and none may be
added without an ADR and a corresponding change to PLT-POL-001 itself —
tests/unit/test_allowed_output_type.py pins the member count and names so
that change can't happen silently in a routine PR.
"""

from enum import StrEnum


class AllowedOutputType(StrEnum):
    FACTUAL_EVIDENCE = "FACTUAL_EVIDENCE"
    CALCULATION_RESULT = "CALCULATION_RESULT"
    USER_DIRECTED_COMPARISON = "USER_DIRECTED_COMPARISON"
    DOCUMENT_EXPLANATION = "DOCUMENT_EXPLANATION"
    OBJECTIVE_EVENT = "OBJECTIVE_EVENT"
    USER_RULE_ALERT = "USER_RULE_ALERT"
    SOURCE_DISCOVERY = "SOURCE_DISCOVERY"
    NEUTRAL_EDUCATION = "NEUTRAL_EDUCATION"
