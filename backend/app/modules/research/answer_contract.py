"""G04: the "published response" half of the typed identity/capability/
answer contract (UAT gap analysis, 07/ENGINEERING REMEDIATION). Builds on
identity_contract.py's CapabilityDecision and on the real evidence.*
tables (EvidenceBundle/EvidenceMember) rather than inventing a parallel
evidence shape - "claims and evidence references" in the spec means a
claim binds to an actual EvidenceMember row, never a bare string citation.

"Validate before rendering" (the spec's own words) is validate_before_render
below: every claim in every block must resolve to a real EvidenceMember
that is actually IN the bundle being published, and the bundle itself must
be READY. This is what REG-02's acceptance categories are checking for -
mismatched citation/version and source injection are exactly "a claim
points somewhere that isn't a real member of this bundle"; unsupported
claim and revoked rights are "a response claims content it isn't entitled
to show."
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.research.identity_contract import CapabilityState

# Capability states that must never carry a rendered claim - an
# UNSUPPORTED/RESTRICTED/STALE/TEMPORARILY_UNAVAILABLE/CONFLICTED decision
# means "there's nothing admissible to show," so a response in one of these
# states that still carries claims is the "unsupported claim" / "revoked
# rights" defect REG-02 names, not a feature.
_STATES_REQUIRING_EMPTY_BLOCKS = frozenset(
    {
        CapabilityState.UNSUPPORTED,
        CapabilityState.RESTRICTED,
        CapabilityState.STALE,
        CapabilityState.TEMPORARILY_UNAVAILABLE,
        CapabilityState.CONFLICTED,
    }
)


class BlockType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"


@dataclass(frozen=True)
class Claim:
    """One factual assertion, bound to exactly one evidence member it is
    based on - never a bare string citation."""

    text: str
    evidence_member_id: uuid.UUID


@dataclass(frozen=True)
class AnswerBlock:
    block_type: BlockType
    content: dict[str, object]
    claims: list[Claim] = field(default_factory=list)


@dataclass(frozen=True)
class PublishedResponse:
    answer_id: uuid.UUID
    version: int
    evidence_bundle_id: uuid.UUID
    capability_state: CapabilityState
    blocks: list[AnswerBlock]
    published_at: dt.datetime
    coverage_as_of: dt.datetime | None = None


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str]


async def validate_before_render(
    session: AsyncSession, response: PublishedResponse
) -> ValidationResult:
    errors: list[str] = []

    bundle = await session.get(EvidenceBundle, response.evidence_bundle_id)
    if bundle is None:
        return ValidationResult(
            ok=False, errors=[f"evidence_bundle {response.evidence_bundle_id} does not exist"]
        )
    if bundle.status != "READY":
        errors.append(
            f"evidence_bundle {bundle.id} is {bundle.status}, not READY - "
            "nothing may be published from a bundle that isn't ready"
        )

    member_ids_in_bundle = set(
        (
            await session.execute(
                select(EvidenceMember.id).where(
                    EvidenceMember.evidence_bundle_id == response.evidence_bundle_id
                )
            )
        )
        .scalars()
        .all()
    )

    all_claims = [claim for block in response.blocks for claim in block.claims]

    if response.capability_state in _STATES_REQUIRING_EMPTY_BLOCKS and all_claims:
        errors.append(
            f"capability_state is {response.capability_state.value} but the response "
            f"carries {len(all_claims)} claim(s) - an unsupported/restricted/stale/"
            "conflicted answer must not render admissible-looking content"
        )

    for claim in all_claims:
        if claim.evidence_member_id not in member_ids_in_bundle:
            errors.append(
                f"claim {claim.text!r} cites evidence_member "
                f"{claim.evidence_member_id}, which is not a member of bundle "
                f"{response.evidence_bundle_id} - mismatched citation or source injection"
            )

    return ValidationResult(ok=not errors, errors=errors)
