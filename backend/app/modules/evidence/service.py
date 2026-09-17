"""Assembles a research answer (P1 week 13) — this is `POST /api/v1/research`'s
actual logic, gated through the PDP before any content reaches a caller.

Ports mockReply.ts's four-way intent classification (advice-redirect /
accrued-interest-explanation / gilt-facts / default) verbatim — that's
genuinely correct product behaviour worth keeping, per the plan this was
built from — but every branch now queries real accepted_fact/
calculation_result rows instead of returning canned text, and every
response (including the advice-redirect, which used to be a client-side
regex match) is evaluated through the PDP against AllowedOutputType first.

A fifth branch (yield-curve) was added afterward, once BoE curve data was
live: the curve's own points are real, directly-published, reconciled
facts in their own right (FACTUAL_EVIDENCE), not merely an input to the
gilt-facts branch's model-implied price — a user asking specifically about
"the yield curve" deserves the actual curve, not just the one derived
number it feeds into elsewhere.

A sixth branch (help) answers meta-questions about what the platform
covers ("what topics do you answer") with an honest, current capability
list, rather than the generic "no reconciled data" default — that default
reads as evasive for a question about the platform itself, not about a
missing fact. Checked right after advice, since a genuine capability
question is a different kind of thing from a request for financial data.

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
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calculation.models import CalculationResult
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.evidence.models import EvidenceBundle, EvidenceMember
from app.modules.market.freshness import compute_freshness
from app.modules.market.models import AcceptedFact
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
)
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.market.queries import current_accepted_fact_at
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
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_ACCRUED_PATTERN = re.compile(
    r"accrued|day count|convention|clean|dirty|act/act|ex[- ]?dividend", re.I
)
_YIELD_CURVE_PATTERN = re.compile(
    r"yield curve|spot curve|interest rates?\b|bank of england|\bboe\b", re.I
)
# Deliberately specific phrasings only (not a bare "help") - a genuine data
# question like "can you help me understand accrued interest" must still
# reach the accrued-interest branch, not this one ("help me [do something]"
# doesn't match; only the generic, topic-less "help with" / "what can/do
# you ..." phrasings do).
_HELP_PATTERN = re.compile(
    r"which topics|what topics|what (can|do) (you|u) (do|answer|cover|know)|"
    r"help with\b|what (are|is) your capabilit", re.I,
)


def _is_advice(text: str) -> bool:
    return any(p.search(text) for p in _ADVICE_PATTERNS)


def _is_help_request(text: str) -> bool:
    return bool(_HELP_PATTERN.search(text))


def _mentions_gilt(text: str) -> bool:
    return bool(_GILT_PATTERN.search(text))


def _mentioned_year(text: str) -> int | None:
    match = _YEAR_PATTERN.search(text)
    return int(match.group()) if match else None


def _mentions_yield_curve(text: str) -> bool:
    return bool(_YIELD_CURVE_PATTERN.search(text))


def _mentions_accrued(text: str) -> bool:
    return bool(_ACCRUED_PATTERN.search(text))


@dataclass(frozen=True)
class Citation:
    label: str
    meta: str | None
    pill: str  # CURRENT | DELAYED | STALE | UNAVAILABLE | SOURCE - mirrors frontend's Freshness
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


def _help_reply() -> ResearchAnswer:
    return ResearchAnswer(
        text=(
            "Right now I can answer from real, reconciled data on:\n\n"
            "- UK gilt reference terms — currently the 4¼% Treasury Stock 2036 "
            "(coupon, maturity, day count and other accepted facts)\n"
            "- The Bank of England's UK nominal gilt spot curve — their published "
            "interest-rate curve, updated daily\n"
            "- Accrued interest, clean vs dirty price, and ex-dividend methodology — "
            "general explanations, not tied to live data\n\n"
            "I never give investment recommendations, price targets, or buy/sell/hold "
            "guidance — that's a structural limit of the platform, not a missing "
            "feature."
        ),
        facts=None,
        citations=[],
        note=None,
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


async def _gilt_facts_reply(session: AsyncSession, query_text: str) -> ResearchAnswer:
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
    reference_fact = await current_accepted_fact_at(
        session, subject_id=instrument.id, metric_id=METRIC_GILT_REFERENCE_TERMS, at=now
    )
    if reference_fact is None:
        return _default_reply("gilt reference facts")

    # Only one gilt exists in the platform right now, but the query pattern
    # matches ANY "gilt" mention - without this check, asking about a
    # completely different gilt (e.g. "the 2065 gilt") would silently show
    # this one's facts as if they answered the question. That's worse than
    # the honest "no data" default: it's actively misleading, not just
    # unhelpful. A mentioned year that doesn't match this instrument's own
    # maturity year means the question is about a DIFFERENT instrument.
    mentioned_year = _mentioned_year(query_text)
    maturity_year = dt.date.fromisoformat(reference_fact.value["redemption_date"]).year
    if mentioned_year is not None and mentioned_year != maturity_year:
        return ResearchAnswer(
            text=(
                f"I don't have reconciled data for a gilt maturing in {mentioned_year} yet "
                f"— currently only {reference_fact.value['instrument_name']} (maturing "
                f"{maturity_year}) is live on the platform."
            ),
            facts=None,
            citations=[],
            note=None,
            allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
            evidence_bundle_id=None,
        )

    rows: list[tuple[str, str]] = [
        ("Instrument", reference_fact.value["instrument_name"]),
        ("ISIN", SEED_GILT_ISIN),
        ("Coupon", f"{reference_fact.value['coupon_rate']}% semi-annual"),
        ("Maturity", reference_fact.value["redemption_date"]),
        ("Day count", "ACT/ACT (ICMA)"),
        ("Currency", "GBP"),
    ]
    assert reference_fact.knowledge_range.lower is not None  # our own rows always set this
    reference_knowledge_time = reference_fact.knowledge_range.lower
    citations = [
        Citation(
            label="UK DMO — Gilts in Issue",
            meta=f"Accepted fact, knowledge-time {reference_knowledge_time.isoformat()}",
            pill=compute_freshness(
                metric_id=METRIC_GILT_REFERENCE_TERMS,
                knowledge_time=reference_knowledge_time,
                now=now,
            ),
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


_BENCHMARK_TENORS: list[tuple[Decimal, str]] = [
    (Decimal("1"), "1Y"),
    (Decimal("2"), "2Y"),
    (Decimal("5"), "5Y"),
    (Decimal("10"), "10Y"),
    (Decimal("20"), "20Y"),
    (Decimal("30"), "30Y"),
]


async def _latest_curve_date(session: AsyncSession) -> dt.datetime | None:
    return (
        await session.execute(
            select(func.lower(AcceptedFact.valid_range))
            .where(
                AcceptedFact.subject_type == SUBJECT_TYPE_YIELD_CURVE_POINT,
                AcceptedFact.metric_id == METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                AcceptedFact.status == "ACTIVE",
            )
            .order_by(func.lower(AcceptedFact.valid_range).desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _curve_point_facts_at(session: AsyncSession, *, at: dt.datetime) -> list[AcceptedFact]:
    return list(
        (
            await session.execute(
                select(AcceptedFact).where(
                    AcceptedFact.subject_type == SUBJECT_TYPE_YIELD_CURVE_POINT,
                    AcceptedFact.metric_id == METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                    AcceptedFact.status == "ACTIVE",
                    AcceptedFact.valid_range.contains(at),
                )
            )
        )
        .scalars()
        .all()
    )


async def _yield_curve_reply(session: AsyncSession) -> ResearchAnswer:
    """The curve's own points, not the gilt-facts branch's model-implied
    price derived FROM them — these are real, directly-published, reconciled
    facts (FACTUAL_EVIDENCE) in their own right, so a user asking about the
    curve gets the curve, not just the one derived number it feeds into
    elsewhere.
    """
    if not await _display_allowed(session, "boe.yield-curve"):
        return _default_reply("UK yield curve")

    latest_date = await _latest_curve_date(session)
    if latest_date is None:
        return _default_reply("UK yield curve")

    curve_facts = await _curve_point_facts_at(session, at=latest_date)
    if not curve_facts:
        return _default_reply("UK yield curve")

    by_tenor = {Decimal(f.value["tenor_years"]): f for f in curve_facts}
    rows: list[tuple[str, str]] = []
    used_facts: list[AcceptedFact] = []
    for tenor, label in _BENCHMARK_TENORS:
        fact = by_tenor.get(tenor)
        if fact is None:
            continue
        rows.append((label, f"{fact.value['spot_rate_pct']}%"))
        used_facts.append(fact)

    if not rows:
        return _default_reply("UK yield curve")

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION",
        knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    for fact in used_facts:
        session.add(
            EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=fact.id)
        )

    as_of = latest_date.date().isoformat()
    # The oldest knowledge-time among the points actually shown, not the
    # newest: a curve pill must never claim to be fresher than its
    # least-fresh contributing point.
    oldest_knowledge_time = min(
        fact.knowledge_range.lower for fact in used_facts if fact.knowledge_range.lower is not None
    )
    return ResearchAnswer(
        text=(
            f"Here is the Bank of England's UK nominal gilt spot curve as of {as_of} "
            "— the government's own published interest-rate curve, not any specific "
            "instrument's price."
        ),
        facts=FactTable(title="UK nominal gilt spot curve (Bank of England)", rows=rows),
        citations=[
            Citation(
                label="Bank of England — daily nominal gilt spot curve",
                meta=f"Published {as_of} — Open Government Licence v3.0",
                pill=compute_freshness(
                    metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
                    knowledge_time=oldest_knowledge_time,
                ),
                kind="doc",
            )
        ],
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
    elif _is_help_request(query_text):
        answer = _help_reply()
    elif _mentions_accrued(query_text):
        answer = _accrued_reply()
    elif _mentions_yield_curve(query_text):
        answer = await _yield_curve_reply(session)
    elif _mentions_gilt(query_text):
        answer = await _gilt_facts_reply(session, query_text)
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


# ------------------------------------------------------------------ GET evidence


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    subject_type: str | None
    metric_id: str | None
    value: dict[str, object] | None
    basis: str | None
    as_of: str | None


@dataclass(frozen=True)
class EvidenceDetail:
    evidence_bundle_id: uuid.UUID
    purpose_type: str
    status: str
    items: list[EvidenceItem]


async def is_message_visible(session: AsyncSession, *, message_id: uuid.UUID) -> bool:
    """True only if the message exists AND belongs to the caller's own
    account — RLS (applied per-request by identity.apply_rls_context)
    already filters out anyone else's rows, so a plain existence check is
    enough; there is no separate "exists but isn't yours" branch to write.
    """
    row = (
        await session.execute(
            text("SELECT 1 FROM research.message WHERE id = :id"), {"id": str(message_id)}
        )
    ).first()
    return row is not None


async def get_evidence_for_message(
    session: AsyncSession, *, message_id: uuid.UUID
) -> EvidenceDetail | None:
    """None means this message genuinely has no evidence bundle - a normal
    case (e.g. an advice-redirect reply never assembles one), not an error.
    Callers must check is_message_visible() separately for the 404 case;
    this function assumes visibility has already been established.
    """
    bundle = (
        await session.execute(
            select(EvidenceBundle).where(EvidenceBundle.research_message_id == message_id)
        )
    ).scalar_one_or_none()
    if bundle is None:
        return None

    members = (
        await session.execute(
            select(EvidenceMember).where(EvidenceMember.evidence_bundle_id == bundle.id)
        )
    ).scalars().all()

    items: list[EvidenceItem] = []
    for member in members:
        if member.kind == "FACT" and member.accepted_fact_id is not None:
            fact = await session.get(AcceptedFact, member.accepted_fact_id)
            if fact is not None:
                assert fact.knowledge_range.lower is not None  # our own rows always set this
                items.append(
                    EvidenceItem(
                        kind="FACT",
                        subject_type=fact.subject_type,
                        metric_id=fact.metric_id,
                        value=fact.value,
                        basis=None,
                        as_of=fact.knowledge_range.lower.isoformat(),
                    )
                )
        elif member.kind == "CALCULATION" and member.calculation_result_id is not None:
            result = await session.get(CalculationResult, member.calculation_result_id)
            if result is not None:
                items.append(
                    EvidenceItem(
                        kind="CALCULATION",
                        subject_type=result.subject_type,
                        metric_id=result.metric_id,
                        value=result.value,
                        basis=result.basis,
                        as_of=result.as_of_date.isoformat(),
                    )
                )

    return EvidenceDetail(
        evidence_bundle_id=bundle.id,
        purpose_type=bundle.purpose_type,
        status=bundle.status,
        items=items,
    )
