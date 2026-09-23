"""AI-001 A1's EvidenceBundle input contract: turns an already-assembled
evidence.EvidenceBundle into the only text a model call is allowed to
treat as fact, plus the instruction that tells it so.

Assembling/retrieving evidence is EVID-001's job, not this module's - the
Gateway is explicitly barred from its own open-ended retrieval (AI-001
§8, "The AI Gateway does not perform open-ended retrieval from internal
stores"). This module only renders a bundle some other caller (a script,
a future /research wiring, a monitoring-alert explainer) has already
assembled and handed over by ID.

A missing or empty bundle is a hard reject, not a degrade-to-ungrounded
fallback (AI-001 §23: "empty evidence bundle -> never generate a
speculative answer") - see gateway.invoke_model, which refuses the call
outright rather than calling a provider with no evidence attached.

(A6 hardening, 2026-09-23) A rendered prompt over _MAX_PROMPT_CHARS is
also a hard reject, never a silent truncation - AI-001's 14-step
pipeline names "invoke model (bounded context)" as its own step, and
truncating evidence risks citing an index that got cut off, which would
be worse than refusing outright. The bound is a deliberate product
policy (cost/predictability), not a technical model-context-window
limit - both configured models support far larger contexts than this.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.service import EvidenceItem, get_evidence_bundle_items

_GROUNDING_INSTRUCTION = (
    "You must answer using ONLY the numbered evidence items below. Cite the "
    "item number in brackets, e.g. [1], for every factual claim you make. If "
    "the evidence does not contain enough information to answer, say so "
    "explicitly rather than drawing on outside knowledge. Do not state or "
    "imply any investment recommendation, price target, ranking, or "
    "suitability conclusion under any circumstances."
)

# ~5k tokens at a conservative 4 chars/token - a policy bound, see module
# docstring, not a technical limit either configured model actually has.
_MAX_PROMPT_CHARS = 20_000


class BundleTooLarge(Exception):
    """The bundle rendered to more than _MAX_PROMPT_CHARS - refuse rather
    than silently truncate (see module docstring)."""


def _render_item(index: int, item: EvidenceItem) -> str:
    value_text = ", ".join(f"{k}: {v}" for k, v in (item.value or {}).items())
    basis = f" (basis: {item.basis})" if item.basis else ""
    return f"[{index}] {item.kind} — {item.metric_id}{basis}, as of {item.as_of}: {value_text}"


@dataclass(frozen=True)
class GroundedPrompt:
    text: str
    evidence_item_count: int


async def render_grounded_prompt(
    session: AsyncSession, *, bundle_id: uuid.UUID, instruction: str
) -> GroundedPrompt | None:
    """None means the bundle is missing or has no renderable items - the
    caller must reject the call, never fall back to an ungrounded prompt.
    Raises BundleTooLarge instead of returning, for the same "must
    reject, never silently degrade" reason - a distinct signal so a
    caller (gateway.py) can give an accurate rejection reason rather than
    conflating "no evidence" with "too much evidence".
    """
    items = await get_evidence_bundle_items(session, bundle_id=bundle_id)
    if not items:
        return None

    rendered_items = "\n".join(_render_item(i, item) for i, item in enumerate(items, start=1))
    text = f"{_GROUNDING_INSTRUCTION}\n\nEvidence:\n{rendered_items}\n\nTask: {instruction}"
    if len(text) > _MAX_PROMPT_CHARS:
        raise BundleTooLarge(
            f"bundle {bundle_id} rendered to {len(text)} chars, over the "
            f"{_MAX_PROMPT_CHARS}-char bounded-context limit"
        )
    return GroundedPrompt(text=text, evidence_item_count=len(items))
