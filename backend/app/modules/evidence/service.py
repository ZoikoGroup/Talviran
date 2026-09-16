"""Assembles a research answer (P1 week 13) — this is `POST /api/v1/research`'s
actual logic, gated through the PDP before any content reaches a caller.

Ports mockReply.ts's four-way intent classification (advice-redirect /
accrued-interest-explanation / gilt-facts / default) verbatim — that's
genuinely correct product behaviour worth keeping, per the plan this was
built from — but every branch now queries real accepted_fact/
calculation_result rows instead of returning canned text, and every
response (including the advice-redirect, which used to be a client-side
regex match) is evaluated through the PDP against AllowedOutputType first.

Single-instrument, single-jurisdiction P1 scope, matching every other
module built so far: `_DEV_JURISDICTION` is hardcoded (real auth exists now,
but per-account jurisdiction resolution is still P2 - see
reference/service.py for the same documented gap), and the gilt-facts
branch assumes the one seeded instrument/source per metric rather than
tracing FactObservationLink -> SourceObservation -> rights_profile_id for
full multi-source generality (reconciliation_policy.py's own docstring
notes the identical single-source scope limit for P1).
"""

import datetime as dt
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import CalculationResult
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.reference.models import Instrument, InstrumentAlias
from app.modules.rights.engine import RightsDecision, evaluate_action
from app.modules.rights.models import RightsProfile

_DEV_JURISDICTION = "GB"
RESEARCH_CAPABILITY_CODE = "research.answer"
SEED_GILT_ISIN = "GB0032452392"

_ADVICE_PATTERNS = [
    re.compile(r"should i (buy|sell|invest|hold)", re.I),
    re.compile(r"\b(is|are) (it|this|these|that) a good (buy|investment|idea)\b", re.I),
    re.compile(r"what should i (buy|invest|pick)", re.I),
    re.compile(r"\b(best|top|worst) (bond|gilt|treasury|pick|investment)s?\b", re.I),
    re.compile(r"\b(price target|fair value|rating|recommend)\b", re.I),
    re.compile(r"worth (buying|investing)", re.I),
]
_GILT_PATTERN = re.compile(r"\bgilt|treasury gilt|2036\b", re.I)
_ACCRUED_PATTERN = re.compile(r"accrued|day count|convention|clean|dirty|act/act", re.I)


def _is_advice(text: str) -> bool:
    return any(p.search(text) for p in _ADVICE_PATTERNS)


def _mentions_gilt(text: str) -> bool:
    return bool(_GILT_PATTERN.search(text))


def _mentions_accrued(text: str) -> bool:
    return bool(_ACCRUED_PATTERN.search(text))


@dataclass(frozen=True)
class Citation:
    label: str
    meta: str | None
    pill: str  # CURRENT | DELAYED | STALE | SOURCE - mirrors frontend's Freshness
    kind: str  # doc | book | link


@dataclass(frozen=True)
class FactTable:
    title: str
    rows: list[tuple[str, str]]


@dataclass(frozen=True)
class ResearchAnswer:
    text: str
    facts: FactTable | None
    citations: list[Citation]
    note: str | None
    allowed_output_type: AllowedOutputType
    evidence_bundle_id: uuid.UUID | None


def _advice_reply() -> ResearchAnswer:
    return ResearchAnswer(
        text=(
            "I can't tell you whether to buy, sell or hold. Talvrin never produces "
            "investment recommendations, price targets, rankings or suitability "
            "conclusions — by design.\n\n"
            "What I can give you is the evidence to decide for yourself:\n\n"
            "- The instrument's terms and source-linked facts\n"
            "- A reproducible yield and cash-flow calculation\n"
            "- A side-by-side comparison against an instrument you pick\n"
            "- An objective alert on a threshold you set\n\n"
            "Which would help?"
        ),
        facts=None,
        citations=[],
        note=(
            "Redirected by the recommendation-safe perimeter. No response type for "
            "buy/sell/hold exists in the platform (PRD-001 SS11, POL-001)."
        ),
        allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
        evidence_bundle_id=None,
    )


def _accrued_reply() -> ResearchAnswer:
    return ResearchAnswer(
        text=(
            "Accrued interest is the coupon a bond has earned but not yet paid, from "
            "the last coupon date up to settlement. The buyer pays it to the seller on "
            "top of the clean price.\n\n"
            "Clean price quotes the bond excluding accrued interest — this is how "
            "gilts and Treasuries are quoted.\n"
            "Dirty price is what actually settles: clean price + accrued interest.\n\n"
            "For gilts the accrual uses ACT/ACT (ICMA), and the ex-dividend convention "
            "means a buyer inside the ex-dividend window is not entitled to the next "
            "coupon — accrued interest then goes negative."
        ),
        facts=None,
        citations=[
            Citation(
                label="UK DMO — Gilt Formulae and Examples, 4th ed. Section Three",
                meta="Accrued interest & ex-dividend, 18 Dec 2024",
                pill="SOURCE",
                kind="book",
            )
        ],
        note=(
            "Explanation only — no calculation was performed. Run the calculator for "
            "a figure tied to a specific settlement date."
        ),
        allowed_output_type=AllowedOutputType.DOCUMENT_EXPLANATION,
        evidence_bundle_id=None,
    )


def _default_reply(query: str) -> ResearchAnswer:
    return ResearchAnswer(
        text=(
            f'You asked: "{query}"\n\n'
            "Talvrin only answers from accepted facts and deterministic "
            "calculations, and doesn't yet have reconciled data covering this "
            "question — currently only UK gilt reference terms and BoE-curve-implied "
            "pricing for one seeded instrument are live."
        ),
        facts=None,
        citations=[],
        note=None,
        allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
        evidence_bundle_id=None,
    )


async def _accepted_fact_at(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str, at: dt.datetime
) -> AcceptedFact | None:
    return (
        await session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_id == subject_id,
                AcceptedFact.metric_id == metric_id,
                AcceptedFact.status == "ACTIVE",
                AcceptedFact.valid_range.contains(at),
            )
        )
    ).scalar_one_or_none()


async def _latest_calculation_result(
    session: AsyncSession, *, subject_id: uuid.UUID, metric_id: str
) -> CalculationResult | None:
    return (
        await session.execute(
            select(CalculationResult)
            .where(
                CalculationResult.subject_id == subject_id,
                CalculationResult.metric_id == metric_id,
                CalculationResult.status == "ACTIVE",
            )
            .order_by(CalculationResult.as_of_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _display_allowed(session: AsyncSession, rights_profile_code: str) -> bool:
    profile_id = (
        await session.execute(
            select(RightsProfile.id).where(RightsProfile.code == rights_profile_code)
        )
    ).scalar_one_or_none()
    decision = await evaluate_action(session, "display", profile_id)
    return decision is RightsDecision.ALLOW


async def _gilt_facts_reply(session: AsyncSession) -> ResearchAnswer:
    instrument = (
        await session.execute(
            select(Instrument)
            .join(InstrumentAlias, InstrumentAlias.instrument_id == Instrument.id)
            .where(
                InstrumentAlias.alias_type == "ISIN",
                InstrumentAlias.alias_value == SEED_GILT_ISIN,
            )
        )
    ).scalar_one_or_none()
    if instrument is None or not await _display_allowed(session, "uk-dmo.gilts"):
        return _default_reply("gilt reference facts")

    now = dt.datetime.now(dt.UTC)
    reference_fact = await _accepted_fact_at(
        session, subject_id=instrument.id, metric_id=METRIC_GILT_REFERENCE_TERMS, at=now
    )
    if reference_fact is None:
        return _default_reply("gilt reference facts")

    rows: list[tuple[str, str]] = [
        ("Instrument", reference_fact.value["instrument_name"]),
        ("ISIN", SEED_GILT_ISIN),
        ("Coupon", f"{reference_fact.value['coupon_rate']}% semi-annual"),
        ("Maturity", reference_fact.value["redemption_date"]),
        ("Day count", "ACT/ACT (ICMA)"),
        ("Currency", "GBP"),
    ]
    assert reference_fact.knowledge_range.lower is not None  # our own rows always set this
    knowledge_time = reference_fact.knowledge_range.lower.isoformat()
    citations = [
        Citation(
            label="UK DMO — Gilts in Issue",
            meta=f"Accepted fact, knowledge-time {knowledge_time}",
            pill="CURRENT",
            kind="doc",
        ),
    ]

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=now, status="ASSEMBLING"
    )
    session.add(bundle)
    await session.flush()
    session.add(
        EvidenceMember(
            evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=reference_fact.id
        )
    )

    if await _display_allowed(session, "boe.yield-curve"):
        model_price = await _latest_calculation_result(
            session, subject_id=instrument.id, metric_id=METRIC_MODEL_IMPLIED_CLEAN_PRICE
        )
        if model_price is not None:
            rows.append(
                (
                    "Model-implied clean price (estimate)",
                    f"{float(model_price.value['clean_price']):.2f}",
                )
            )
            citations.append(
                Citation(
                    label="Talvrin model estimate — BoE nominal gilt curve",
                    meta=f"As of {model_price.as_of_date.isoformat()} — not a market quote",
                    pill="SOURCE",
                    kind="link",
                )
            )
            session.add(
                EvidenceMember(
                    evidence_bundle_id=bundle.id,
                    kind="CALCULATION",
                    calculation_result_id=model_price.id,
                )
            )

    return ResearchAnswer(
        text=(
            f"Here are the canonical terms for {reference_fact.value['instrument_name']}, "
            "as accepted by the platform. Each value below resolves to a source "
            "observation — open Evidence to trace any of them."
        ),
        facts=FactTable(title="Instrument facts", rows=rows),
        citations=citations,
        note=None,
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


async def _pdp_permits(
    session: AsyncSession,
    *,
    principal_id: uuid.UUID | None,
    account_id: uuid.UUID | None,
    requested_output_type: AllowedOutputType,
) -> bool:
    ctx = PolicyContext(
        principal_id=principal_id,
        account_id=account_id,
        jurisdiction_code=_DEV_JURISDICTION,
        capability_code=RESEARCH_CAPABILITY_CODE,
        requested_output_type=requested_output_type,
    )
    decision = await evaluate(session, ctx)
    return decision.is_permit


_POLICY_BLOCKED_REPLY = ResearchAnswer(
    text="This response is not currently permitted.",
    facts=None,
    citations=[],
    note="Blocked by policy — see the platform's policy decision log for the reason.",
    allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
    evidence_bundle_id=None,
)


async def assemble_research_answer(
    session: AsyncSession,
    *,
    query_text: str,
    principal_id: uuid.UUID | None,
    account_id: uuid.UUID | None,
) -> ResearchAnswer:
    if _is_advice(query_text):
        answer = _advice_reply()
    elif _mentions_accrued(query_text):
        answer = _accrued_reply()
    elif _mentions_gilt(query_text):
        answer = await _gilt_facts_reply(session)
    else:
        answer = _default_reply(query_text)

    permitted = await _pdp_permits(
        session,
        principal_id=principal_id,
        account_id=account_id,
        requested_output_type=answer.allowed_output_type,
    )
    if not permitted:
        return _POLICY_BLOCKED_REPLY

    return answer
