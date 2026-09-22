"""AI-001 A2: validates a model's raw text response before invoke_model
hands it back to a caller. Two checks, both deterministic and cheap
(AI-001 §12.2 - a pattern-based perimeter scanner is explicitly
defense-in-depth only, never the sole control; the primary control is
that no recommendation output type exists for the model to be asked
for in the first place - see policy.allowed_output_type):

1. Citation validity - every `[N]` marker in the response must reference
   an evidence item that was actually in the grounded prompt (AI-001
   §14.2's grounding rule: a claim can only be as good as the evidence it
   cites). A response with zero citations is NOT a failure on its own -
   evidence_path's grounding instruction explicitly permits "the evidence
   doesn't contain enough information" as a valid, citation-free answer.
2. Recommendation-perimeter scan - catches a model volunteering
   advice-shaped language (buy/sell/hold framing, target price, top
   pick, suitability, credit rating, rebalancing) even when the query
   itself wasn't advice-seeking. The empirical basis for this check: a
   live report run 2026-09-22 through both providers showed exactly this
   failure mode - both models added unsolicited "Recommendation:" /
   "makes sense for investors" framing to a factual-sounding prompt.

gateway.invoke_model does exactly one regeneration attempt on failure,
then rejects rather than serving invalid text (AI-001 §23).
"""

import re
from dataclasses import dataclass, field

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")

_PERIMETER_PATTERNS = [
    re.compile(r"\bi (recommend|would recommend)\b", re.I),
    re.compile(r"^\s*\**recommendation\**\s*:", re.I | re.M),
    re.compile(r"\byou should (buy|sell|hold)\b", re.I),
    re.compile(r"\b(strong|highly rated)?\s*(buy|sell|hold) rating\b", re.I),
    re.compile(r"\btarget price\b", re.I),
    re.compile(r"\btop pick\b", re.I),
    re.compile(r"\bbest (buy|investment|gilt|treasury|choice)\b", re.I),
    re.compile(r"\bsuitab(le|ility)\b", re.I),
    re.compile(r"\bcredit rating\b", re.I),
    re.compile(r"\b(rebalance|model portfolio)\b", re.I),
    re.compile(r"\bmakes sense for investors\b", re.I),
]


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    failure_reasons: list[str] = field(default_factory=list)


def _citation_failures(text: str, *, evidence_item_count: int) -> list[str]:
    cited = {int(m.group(1)) for m in _CITATION_PATTERN.finditer(text)}
    out_of_range = sorted(n for n in cited if n < 1 or n > evidence_item_count)
    if not out_of_range:
        return []
    return [
        f"cited evidence item(s) {out_of_range} do not exist in the "
        f"{evidence_item_count}-item evidence bundle given to the model"
    ]


def _perimeter_failures(text: str) -> list[str]:
    hits = [p.pattern for p in _PERIMETER_PATTERNS if p.search(text)]
    if not hits:
        return []
    return [f"response contains recommendation-shaped language: {hits}"]


def validate_response(text: str, *, evidence_item_count: int) -> ValidationResult:
    reasons = _citation_failures(text, evidence_item_count=evidence_item_count)
    reasons += _perimeter_failures(text)
    return ValidationResult(is_valid=not reasons, failure_reasons=reasons)
