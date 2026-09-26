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
module built so far: `DEV_JURISDICTION` is hardcoded (real auth exists now,
but per-account jurisdiction resolution is still P2 - see
reference/service.py for the same documented gap), and the gilt-facts
branch assumes the one seeded instrument/source per metric rather than
tracing FactObservationLink -> SourceObservation -> rights_profile_id for
full multi-source generality (reconciliation_policy.py's own docstring
notes the identical single-source scope limit for P1). Exported (not
`_`-prefixed) because api/v1/research.py's own PDP-gated ai_gateway call
needs the exact same value - one shared constant, not two literals that
could silently drift apart.
"""

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.calculation.models import CalculationResult
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.calculation.queries import latest_calculation_result
from app.modules.evidence.embeddings.gemini_client import GeminiEmbeddingError
from app.modules.evidence.models import (
    CitationLocator,
    Document,
    DocumentChunk,
    DocumentVersion,
    EvidenceBundle,
    EvidenceMember,
    ParsedDocumentVersion,
)
from app.modules.evidence.pipeline.embed import search_chunks_by_semantic_query
from app.modules.evidence.queries import search_chunks_by_text
from app.modules.market.freshness import compute_freshness
from app.modules.market.models import AcceptedFact, FactObservationLink, SourceObservation
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
)
from app.modules.market.pipeline.equity_ingest import METRIC_EQUITY_EOD_PRICE
from app.modules.market.pipeline.fx_ingest import METRIC_FX_SPOT_RATE, fx_pair_subject_id
from app.modules.market.pipeline.macro_ingest import macro_series_subject_id
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.market.pipeline.tradeweb_price_ingest import METRIC_GILT_MARKET_CLOSE_PRICE
from app.modules.market.queries import current_accepted_fact_at, latest_accepted_fact
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer
from app.modules.rights.engine import RightsDecision, evaluate_action
from app.modules.rights.models import RightsProfile

DEV_JURISDICTION = "GB"
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
#: "glit" (a real typo hit live: "todays uk glit closing prices") sent a
#: genuine live-price question past this pattern into the document-search
#: catch-all instead of the real gilt-facts/Tradeweb-price branch it should
#: have reached - a materially wrong answer (an unrelated 1999 DMO worked
#: example), not just a missed match. One confirmed, explicit typo
#: alternative added deliberately, not a general fuzzy-match expansion
#: (DATA-002's "no fuzzy identity matching" is about instrument identity
#: resolution specifically, not this kind of intent-vocabulary pattern).
_GILT_PATTERN = re.compile(r"\bgilt|\bglit|treasury gilt|2036\b", re.I)
# Checked BEFORE _GILT_PATTERN below - "Gilt-Edged Market Maker" contains
# the substring "gilt", so without this a genuine market-structure/dealer
# question was silently misrouted to the single-instrument facts branch
# (found live, 2026-09-23, asking about GEMM obligations after the GEMM
# Guidebook was added to the document corpus - it never reached the
# document search that would have actually answered it). This pattern
# doesn't try to be a general topic classifier, just to catch the one
# real ambiguity "gilt" as a substring creates against this specific
# document's own subject matter.
_MARKET_STRUCTURE_PATTERN = re.compile(
    r"market maker|\bgemm\b|primary dealer|going live|\bdmo\b.*(role|obligation)", re.I
)
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_ACCRUED_PATTERN = re.compile(
    r"accrued|day count|convention|clean|dirty|act/act|ex[- ]?dividend", re.I
)
_YIELD_CURVE_PATTERN = re.compile(
    r"yield curve|spot curve|interest rates?\b|bank of england|\bboe\b", re.I
)
# Requires either the unambiguous phrase "exchange rate", or BOTH a
# GBP-side and a USD-side term (either order) - never a single currency
# word alone, which would false-positive on "the dollar cost of..." or
# similar. Only one pair is actually cross-source reconciled today
# (GBP/USD, frankfurter + boe - see reconciliation_policy.FX_SPOT_RATE_
# POLICY), so this deliberately doesn't try to parse an arbitrary pair out
# of free text; _fx_rate_reply always answers with that one canonical pair.
_GBP_TERMS = r"\bgbp\b|\bpound\b|\bpounds\b|\bsterling\b"
_USD_TERMS = r"\busd\b|\bdollar\b|\bdollars\b"
_FX_PATTERN = re.compile(
    rf"exchange rate|(?:{_GBP_TERMS}).*(?:{_USD_TERMS})|(?:{_USD_TERMS}).*(?:{_GBP_TERMS})", re.I
)
# Requires BOTH a metric term (GDP or CPI/inflation) AND a country term -
# only UK/USA are in scope (see memory: an earlier India/NSE equity list
# was a real, flagged scope inconsistency; MACRO_PILOT_SERIES in scripts/
# _connector_registry.py still has 2 India series too, same kind of
# pre-existing leftover, left alone here since nothing routes to them).
# Deliberately no bare "\bus\b" - "us" as a pronoun ("tell us about...")
# would false-positive constantly; "usa"/"united states"/"america" are
# unambiguous instead.
_MACRO_METRIC_TERMS: dict[str, str] = {
    "MACRO_GDP": r"\bgdp\b|gross domestic product",
    "MACRO_CPI": r"\bcpi\b|inflation|consumer price",
}
_MACRO_COUNTRY_TERMS: dict[str, str] = {
    "GBR": r"\buk\b|united kingdom|\bbritain\b|\bbritish\b",
    "USA": r"\busa\b|united states|\bamerica\b|american",
}
_MACRO_SERIES_CODES: dict[tuple[str, str], str] = {
    ("MACRO_GDP", "GBR"): "A-NY.GDP.MKTP.CD-GBR",
    ("MACRO_CPI", "GBR"): "A-FP.CPI.TOTL.ZG-GBR",
    ("MACRO_GDP", "USA"): "A-NY.GDP.MKTP.CD-USA",
    ("MACRO_CPI", "USA"): "A-FP.CPI.TOTL.ZG-USA",
}
# Deliberately specific phrasings only (not a bare "help") - a genuine data
# question like "can you help me understand accrued interest" must still
# reach the accrued-interest branch, not this one ("help me [do something]"
# doesn't match; only the generic, topic-less "help with" / "what can/do
# you ..." phrasings do).
_HELP_PATTERN = re.compile(
    r"which topics|what topics|what (can|do) (you|u) (do|answer|cover|know)|"
    r"help with\b|what (are|is) your capabilit", re.I,
)
# Whole-message match only (never a substring search like the other intent
# patterns) - "hi" as a real word inside an actual question ("this hi-yield
# bond...") must never be mis-routed here. A bare greeting is treated as an
# implicit "what can you help with" - the same honest capability list a
# generic "no data" reply would otherwise cold-open with.
_GREETING_PATTERN = re.compile(
    r"^\s*(hi|hello|hey|hiya|yo|greetings|good (morning|afternoon|evening))\s*[!.]?\s*$", re.I
)
# Same whole-message-only reasoning as _GREETING_PATTERN - "thanks" as a
# real word inside an actual question must never be mis-routed here. Before
# this existed, "thank you" fell all the way through to the cold, generic
# _default_reply ("doesn't yet have reconciled data covering this
# question") - technically correct (no document matches "thank you") but
# an unfriendly, un-conversational answer to what is obviously a closing
# remark, not a data question.
_CLOSING_PATTERN = re.compile(
    r"^\s*(thanks?( you)?( (very|so) much)?|cheers|appreciate it|much appreciated|"
    r"ok(ay)?,?\s*thanks?|great,?\s*thanks?|bye|goodbye|see you|that'?s all)\s*[!.]?\s*$",
    re.I,
)


def _is_advice(text: str) -> bool:
    return any(p.search(text) for p in _ADVICE_PATTERNS)


def _is_help_request(text: str) -> bool:
    return bool(_HELP_PATTERN.search(text))


def _is_greeting(text: str) -> bool:
    return bool(_GREETING_PATTERN.match(text))


def _is_closing(text: str) -> bool:
    return bool(_CLOSING_PATTERN.match(text))


def _mentions_gilt(text: str) -> bool:
    return bool(_GILT_PATTERN.search(text))


def _mentions_market_structure(text: str) -> bool:
    return bool(_MARKET_STRUCTURE_PATTERN.search(text))


def _mentioned_year(text: str) -> int | None:
    match = _YEAR_PATTERN.search(text)
    return int(match.group()) if match else None


def _mentions_yield_curve(text: str) -> bool:
    return bool(_YIELD_CURVE_PATTERN.search(text))


def _mentions_fx(text: str) -> bool:
    return bool(_FX_PATTERN.search(text))


def _mentioned_macro_series(text: str) -> tuple[str, str] | None:
    metric_id = next(
        (m for m, pattern in _MACRO_METRIC_TERMS.items() if re.search(pattern, text, re.I)), None
    )
    if metric_id is None:
        return None
    country = next(
        (c for c, pattern in _MACRO_COUNTRY_TERMS.items() if re.search(pattern, text, re.I)), None
    )
    if country is None:
        return None
    return metric_id, country


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


_CAPABILITY_SUMMARY = (
    "- UK gilt reference terms and real market prices — coupon, maturity, "
    "day count and Tradeweb closing prices across the onboarded gilts\n"
    "- The Bank of England's UK nominal gilt spot curve, and the "
    "model-implied prices derived from it — their published interest-rate "
    "curve, updated daily\n"
    "- GBP/USD exchange rates, US-listed equity prices, and UK/US "
    "macroeconomic indicators (GDP, inflation) — all from real, reconciled "
    "data\n"
    "- Accrued interest, clean vs dirty price, and ex-dividend methodology — "
    "general explanations, not tied to live data\n\n"
    "I never give investment recommendations, price targets, or buy/sell/hold "
    "guidance — that's a structural limit of the platform, not a missing "
    "feature."
)


def _greeting_reply() -> ResearchAnswer:
    # Deliberately one short, conversational line, not the full bulleted
    # _CAPABILITY_SUMMARY (that belongs in _help_reply, for someone who
    # actually asked "what can you do") - a real complaint from live
    # testing: a bulleted capability list with a compliance disclaimer
    # front-loaded onto a bare "hi" reads as a scripted bot, not a chat.
    # Deterministic text, not AI-composed - a greeting has no accepted
    # facts to ground an AI Gateway call against (evidence_bundle_id is
    # None here), and that grounding requirement is a real safety
    # invariant, not something to route around for a friendlier "hi".
    return ResearchAnswer(
        text=(
            "Hey! I'm the Talvrin research assistant — ask me about a "
            "gilt's terms or real price, the BoE yield curve, or how "
            "accrued interest works. What would you like to look into?"
        ),
        facts=None,
        citations=[],
        note=None,
        allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
        evidence_bundle_id=None,
    )


def _closing_reply() -> ResearchAnswer:
    return ResearchAnswer(
        text=(
            "You're welcome! Come back anytime you want to check a gilt's "
            "terms or price, the BoE yield curve, or how accrued interest "
            "works."
        ),
        facts=None,
        citations=[],
        note=None,
        allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
        evidence_bundle_id=None,
    )


def _help_reply() -> ResearchAnswer:
    return ResearchAnswer(
        text=f"Right now I can answer from real, reconciled data on:\n\n{_CAPABILITY_SUMMARY}",
        facts=None,
        citations=[],
        note=None,
        allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
        evidence_bundle_id=None,
    )


_ACCRUED_EXPLANATION_TEXT = (
    "Accrued interest is the coupon a bond has earned but not yet paid, from "
    "the last coupon date up to settlement. The buyer pays it to the seller on "
    "top of the clean price.\n\n"
    "Clean price quotes the bond excluding accrued interest — this is how "
    "gilts and Treasuries are quoted.\n"
    "Dirty price is what actually settles: clean price + accrued interest.\n\n"
    "For gilts the accrual uses ACT/ACT (ICMA), and the ex-dividend convention "
    "means a buyer inside the ex-dividend window is not entitled to the next "
    "coupon — accrued interest then goes negative."
)
_ACCRUED_EXPLANATION_NOTE = (
    "Explanation only — no calculation was performed. Run the calculator for "
    "a figure tied to a specific settlement date."
)


@dataclass(frozen=True)
class _ChunkEvidence:
    document: Document
    bundle_id: uuid.UUID
    citation: Citation


async def _assemble_chunk_evidence(
    session: AsyncSession, chunk: DocumentChunk
) -> _ChunkEvidence | None:
    """Shared by every document-backed reply branch: rights-checks the
    chunk's source document, then builds the real EvidenceBundle/
    EvidenceMember(DOCUMENT_SPAN)/CitationLocator(page) chain a citation
    needs to be more than a label. Returns None - never a wrong or
    invented citation - if the document/version can't be resolved or
    "display" isn't rights-permitted, so callers can fall back to a
    static/no-citation reply (EVID-001 doctrine: an evidence gap degrades
    to "no citation", never a guessed one).
    """
    parsed = await session.get(ParsedDocumentVersion, chunk.parsed_document_version_id)
    version = await session.get(DocumentVersion, parsed.document_version_id) if parsed else None
    if version is None:
        return None
    rights_decision = await evaluate_action(session, "display", version.rights_profile_id)
    if rights_decision is not RightsDecision.ALLOW:
        return None
    document = await session.get(Document, version.document_id)
    if document is None:
        return None

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    locator = CitationLocator(
        document_chunk_id=chunk.id, locator_type="PAGE",
        locator_data={"page": chunk.page_start},
    )
    session.add(locator)
    await session.flush()
    session.add(
        EvidenceMember(
            evidence_bundle_id=bundle.id, kind="DOCUMENT_SPAN",
            document_chunk_id=chunk.id, citation_locator_id=locator.id,
        )
    )
    await session.flush()

    return _ChunkEvidence(
        document=document,
        bundle_id=bundle.id,
        citation=Citation(
            label=document.title,
            meta=f"Page {chunk.page_start}" if chunk.page_start else None,
            pill="SOURCE",
            kind="book",
        ),
    )


async def _document_backed_accrued_reply(session: AsyncSession) -> ResearchAnswer | None:
    """A real, evidence-linked version of _accrued_reply(), citing the
    actual acquired-and-parsed DMO worked-examples document (P4 E1/E2/E3)
    instead of an unlinked source label.
    """
    # "accrued interest" only, not a longer phrase - plainto_tsquery ANDs
    # every word, and a real source page can cover ex-dividend/day-count
    # concepts without using those exact words together on the same page
    # (confirmed against the live-acquired DMO document: "ex-dividend" as
    # a literal token doesn't appear on the page that covers accrued
    # interest worked examples, even though the concept does).
    chunks = await search_chunks_by_text(
        session, query_text="accrued interest", limit=1, min_rank=_MIN_LEXICAL_MATCH_RANK
    )
    if not chunks:
        return None
    evidence = await _assemble_chunk_evidence(session, chunks[0])
    if evidence is None:
        return None

    return ResearchAnswer(
        text=_ACCRUED_EXPLANATION_TEXT,
        facts=None,
        citations=[evidence.citation],
        note=_ACCRUED_EXPLANATION_NOTE,
        allowed_output_type=AllowedOutputType.DOCUMENT_EXPLANATION,
        evidence_bundle_id=evidence.bundle_id,
    )


def _accrued_reply() -> ResearchAnswer:
    """Static fallback - used when no real acquired/parsed/rights-permitted
    document evidence exists yet (e.g. a fresh dev database before
    scripts.ingest_methodology_doc/parse_methodology_doc have run)."""
    return ResearchAnswer(
        text=_ACCRUED_EXPLANATION_TEXT,
        facts=None,
        citations=[
            Citation(
                label="UK DMO — Gilt Formulae and Examples, 4th ed. Section Three",
                meta="Accrued interest & ex-dividend, 18 Dec 2024",
                pill="SOURCE",
                kind="book",
            )
        ],
        note=_ACCRUED_EXPLANATION_NOTE,
        allowed_output_type=AllowedOutputType.DOCUMENT_EXPLANATION,
        evidence_bundle_id=None,
    )


#: Nearest-neighbour vector search always returns *a* closest chunk, even
#: for a query with no real relationship to anything in the corpus -
#: without a cutoff, "hi" confidently "answers" from whatever chunk
#: happens to be least-far-away. Calibrated against real measurements
#: (2026-09-21, gemini-embedding-001 @ 768 dims): irrelevant queries
#: ("hi", "hello", "what's the weather", "thank you", "what's your name",
#: "what stocks should I buy") land at cosine distance 0.49-0.56;
#: genuinely relevant ones ("accrued interest", "redemption yield
#: calculation", a full paraphrased question) land at 0.23-0.33. 0.4 sits
#: in the clear gap between them on every case tested.
#:
#: Re-measured 2026-09-23 after the corpus grew from one document/5
#: chunks to two documents/31 chunks (the GEMM Guidebook added, a
#: genuinely different topic - market structure/dealer obligations, not
#: numeric yield-conversion methodology): the gap held. Relevant queries
#: against EITHER document now land at 0.17-0.29; irrelevant queries at
#: 0.49-0.57. 0.4 still sits cleanly in the middle with room either side
#: - real evidence the threshold generalizes across topics, not just an
#: artifact of the original single-document corpus. Still worth
#: re-measuring again at the next real jump in corpus size/diversity.
_MAX_SEMANTIC_MATCH_DISTANCE = 0.4

#: Real found bug: a worked-examples table page (UK DMO's yldconv.pdf -
#: settlement dates, quasi-coupon dates, decimal yield factors, all packed
#: onto one line per row) dumped verbatim into chat as if it were prose -
#: technically a real excerpt, not fabricated, but unreadable and
#: unprofessional. Calibrated the same way as _MAX_SEMANTIC_MATCH_DISTANCE:
#: measured digit-character density on real chunks (2026-09-24) - genuine
#: prose (GEMM Guidebook, 5 chunks) lands at 0.6%-10.5%; the DMO's own
#: worked-example tables (4 chunks) land at 41.6%-50.9%. 0.2 sits cleanly
#: in the gap.
_MAX_PROSE_DIGIT_RATIO = 0.2

#: Real found bug (2026-09-25): "Lexical AND-matching is its own relevance
#: filter" (this module's own prior assumption, see the comment this
#: replaced) turned out false - plainto_tsquery ANDs on whatever's left
#: after English stopword removal, and a short query can reduce to one
#: common word ("what's your name" -> just "name", "inflation rate" ->
#: "rate"), which then matches ANY chunk containing that word. Two real
#: false positives found live: both questions confidently returned an
#: unrelated GEMM application-form excerpt instead of admitting no match.
#: Calibrated the same way as _MAX_SEMANTIC_MATCH_DISTANCE and
#: _MAX_PROSE_DIGIT_RATIO: measured ts_rank against the real corpus -
#: genuine on-topic matches land at 0.19-0.82; the two real false
#: positives (plus 2 more synthetic bad-query checks) land at 0.002-0.094.
#: 0.15 sits cleanly in the gap.
_MIN_LEXICAL_MATCH_RANK = 0.15


def _looks_like_a_data_table(text: str) -> bool:
    nonspace = [ch for ch in text if not ch.isspace()]
    if not nonspace:
        return False
    digit_ratio = sum(ch.isdigit() for ch in nonspace) / len(nonspace)
    return digit_ratio > _MAX_PROSE_DIGIT_RATIO


async def _document_backed_fallback_reply(
    session: AsyncSession, query_text: str, http: httpx.AsyncClient | None
) -> ResearchAnswer | None:
    """The catch-all branch's last real chance before giving up with
    _default_reply: tries the actual document corpus against the caller's
    real query (not a fixed topic phrase like the accrued-interest
    branch), semantic search first - this is exactly the case semantic
    retrieval earns its keep for, an open-ended paraphrased question that
    a fixed intent pattern was never going to match - then lexical if no
    Gemini key is configured, the embedding call itself fails, or nothing
    semantic clears the relevance bar. Neither retrieval mode failing is a
    request failure, just "no answer found", same as any other
    empty-evidence path in this module.
    """
    settings = get_settings()
    chunks: list[DocumentChunk] = []
    if http is not None and settings.gemini_api_key:
        try:
            chunks = await search_chunks_by_semantic_query(
                session, query_text=query_text, http=http,
                api_key=settings.gemini_api_key, limit=1,
                max_distance=_MAX_SEMANTIC_MATCH_DISTANCE,
            )
        except GeminiEmbeddingError:
            chunks = []
    if not chunks:
        chunks = await search_chunks_by_text(
            session, query_text=query_text, limit=1, min_rank=_MIN_LEXICAL_MATCH_RANK
        )
    if not chunks:
        return None

    chunk = chunks[0]
    evidence = await _assemble_chunk_evidence(session, chunk)
    if evidence is None:
        return None

    excerpt = chunk.text_content.strip()
    if _looks_like_a_data_table(excerpt):
        page_ref = f", page {chunk.page_start}" if chunk.page_start is not None else ""
        body = (
            f"I don't have live reconciled data on this, but the closest match I found "
            f"is a data table in {evidence.document.title}{page_ref} — not something I "
            f"can read out cleanly here. Open the citation below to view it directly."
        )
    else:
        body = (
            f"I don't have live reconciled data on this, but {evidence.document.title} "
            f"covers it:\n\n{excerpt}"
        )

    return ResearchAnswer(
        text=f'You asked: "{query_text}"\n\n{body}',
        facts=None,
        citations=[evidence.citation],
        note=(
            "A raw source excerpt, not a synthesized explanation - "
            "retrieved from the document corpus, not accepted facts or a calculation."
        ),
        allowed_output_type=AllowedOutputType.DOCUMENT_EXPLANATION,
        evidence_bundle_id=evidence.bundle_id,
    )


def _default_reply(query: str) -> ResearchAnswer:
    return ResearchAnswer(
        text=(
            f'You asked: "{query}"\n\n'
            "Talvrin only answers from accepted facts and deterministic "
            "calculations, and doesn't yet have reconciled data covering this "
            "question — currently live: UK gilt terms and real market prices, "
            "the BoE yield curve, GBP/USD exchange rates, US equity prices, and "
            "UK/US macroeconomic indicators."
        ),
        facts=None,
        citations=[],
        note=None,
        allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
        evidence_bundle_id=None,
    )


async def _display_allowed(session: AsyncSession, rights_profile_code: str) -> bool:
    profile_id = (
        await session.execute(
            select(RightsProfile.id).where(RightsProfile.code == rights_profile_code)
        )
    ).scalar_one_or_none()
    decision = await evaluate_action(session, "display", profile_id)
    return decision is RightsDecision.ALLOW


async def _gilts_maturing_in(
    session: AsyncSession, *, year: int, now: dt.datetime
) -> list[tuple[Instrument, AcceptedFact]]:
    """Every onboarded gilt (scripts.onboard_all_gilts) whose CURRENT
    GILT_REFERENCE_TERMS fact redeems in `year` - deterministic only
    (doctrine: no fuzzy identity matching), and can genuinely return more
    than one row: several real UK gilts often share a maturity year (e.g.
    four different gilts mature in 2027), so the caller must handle that
    as an honest disambiguation request, never pick one silently.
    """
    facts = (
        await session.execute(
            select(AcceptedFact).where(
                AcceptedFact.subject_type == "INSTRUMENT",
                AcceptedFact.metric_id == METRIC_GILT_REFERENCE_TERMS,
                AcceptedFact.status == "ACTIVE",
                AcceptedFact.valid_range.contains(now),
                AcceptedFact.value["redemption_date"].astext.startswith(f"{year}-"),
            )
        )
    ).scalars().all()
    out: list[tuple[Instrument, AcceptedFact]] = []
    for fact in facts:
        instrument = await session.get(Instrument, fact.subject_id)
        if instrument is not None:
            out.append((instrument, fact))
    return out


async def _isin_for_instrument(session: AsyncSession, instrument_id: uuid.UUID) -> str | None:
    alias = (
        await session.execute(
            select(InstrumentAlias).where(
                InstrumentAlias.instrument_id == instrument_id,
                InstrumentAlias.alias_type == "ISIN",
            )
        )
    ).scalar_one_or_none()
    return alias.alias_value if alias is not None else None


async def _gilt_facts_reply(session: AsyncSession, query_text: str) -> ResearchAnswer:
    if not await _display_allowed(session, "uk-dmo.gilts"):
        return _default_reply("gilt reference facts")

    now = dt.datetime.now(dt.UTC)
    mentioned_year = _mentioned_year(query_text)

    if mentioned_year is not None:
        # A year was named - resolve among every onboarded gilt, not just
        # the original seed instrument (scripts.onboard_all_gilts widened
        # coverage beyond the single 2036 gilt this branch used to assume
        # was the only one that could ever exist).
        matches = await _gilts_maturing_in(session, year=mentioned_year, now=now)
        if not matches:
            return ResearchAnswer(
                text=f"I don't have reconciled data for a gilt maturing in {mentioned_year}.",
                facts=None, citations=[], note=None,
                allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION, evidence_bundle_id=None,
            )
        if len(matches) > 1:
            isin_by_instrument_id = {
                inst.id: await _isin_for_instrument(session, inst.id) for inst, _ in matches
            }
            # A follow-up reply may repeat back one of the disambiguation
            # options verbatim (its exact instrument_name or ISIN, as shown
            # to the user) - a real bug found via live testing: asking about
            # "2027" then answering "4 1/8% Treasury Gilt 2027" (copied
            # straight from the options just offered) re-triggered the same
            # ambiguous list instead of resolving, because only the year was
            # ever extracted from the query. This is exact substring
            # containment against the canonical name/ISIN, never fuzzy
            # matching (DATA-002: deterministic identity resolution only).
            query_lower = query_text.lower()
            narrowed = []
            for inst, fact in matches:
                isin_for_inst = isin_by_instrument_id[inst.id]
                if fact.value["instrument_name"].lower() in query_lower or (
                    isin_for_inst is not None and isin_for_inst.lower() in query_lower
                ):
                    narrowed.append((inst, fact))
            if len(narrowed) == 1:
                instrument, reference_fact = narrowed[0]
            else:
                name_parts = [
                    f"{fact.value['instrument_name']} ({isin_by_instrument_id[inst.id]})"
                    for inst, fact in matches
                ]
                names = "; ".join(name_parts)
                return ResearchAnswer(
                    text=(
                        f"More than one gilt matures in {mentioned_year}: {names}. "
                        "Which one did you mean?"
                    ),
                    facts=None, citations=[], note=None,
                    allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
                    evidence_bundle_id=None,
                )
        else:
            instrument, reference_fact = matches[0]
    else:
        # No year named - default to the original seed instrument, the
        # same behavior this branch always had for a generic "tell me
        # about the gilt" ask with nothing to disambiguate by.
        seed_instrument = (
            await session.execute(
                select(Instrument)
                .join(InstrumentAlias, InstrumentAlias.instrument_id == Instrument.id)
                .where(
                    InstrumentAlias.alias_type == "ISIN",
                    InstrumentAlias.alias_value == SEED_GILT_ISIN,
                )
            )
        ).scalar_one_or_none()
        if seed_instrument is None:
            return _default_reply("gilt reference facts")
        seed_fact = await current_accepted_fact_at(
            session, subject_id=seed_instrument.id, metric_id=METRIC_GILT_REFERENCE_TERMS, at=now
        )
        if seed_fact is None:
            return _default_reply("gilt reference facts")
        instrument, reference_fact = seed_instrument, seed_fact

    isin = await _isin_for_instrument(session, instrument.id)
    rows: list[tuple[str, str]] = [
        ("Instrument", reference_fact.value["instrument_name"]),
        ("ISIN", isin or "unknown"),
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
        model_price = await latest_calculation_result(
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

    if await _display_allowed(session, "tradeweb.gilt-prices"):
        market_fact = await latest_accepted_fact(
            session, subject_id=instrument.id, metric_id=METRIC_GILT_MARKET_CLOSE_PRICE
        )
        if market_fact is not None:
            rows.append(
                (
                    "Market close price (Tradeweb — real quote)",
                    f"{float(market_fact.value['clean_price']):.2f}",
                )
            )
            assert market_fact.knowledge_range.lower is not None  # our own rows always set this
            market_knowledge_time = market_fact.knowledge_range.lower
            citations.append(
                Citation(
                    label="Tradeweb Market InSite — gilt closing prices",
                    meta=(
                        f"As of {market_knowledge_time.isoformat()} — a real market "
                        "quote, not a model estimate"
                    ),
                    pill=compute_freshness(
                        metric_id=METRIC_GILT_MARKET_CLOSE_PRICE,
                        knowledge_time=market_knowledge_time,
                        now=now,
                    ),
                    kind="doc",
                )
            )
            session.add(
                EvidenceMember(
                    evidence_bundle_id=bundle.id,
                    kind="FACT",
                    accepted_fact_id=market_fact.id,
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


async def _confirming_source_count(session: AsyncSession, accepted_fact_id: uuid.UUID) -> int:
    """How many independently-rights-profiled sources actually back this
    fact - distinct rights_profile_id across its linked observations, since
    every real source in this codebase is seeded under its own RightsProfile
    (frankfurter.fx vs boe.fx-rates, never shared). FactObservationLink's
    own `role` column can't be used for this: reconcile.py writes every
    link as role="PRIMARY" unconditionally, whether the observation was the
    sole source or one of several agreeing ones in the same group, so role
    alone doesn't distinguish "the source" from "a confirming source".
    """
    observation_ids = (
        await session.execute(
            select(FactObservationLink.source_observation_id).where(
                FactObservationLink.accepted_fact_id == accepted_fact_id
            )
        )
    ).scalars().all()
    if not observation_ids:
        return 0
    rights_profile_ids = (
        await session.execute(
            select(SourceObservation.rights_profile_id).where(
                SourceObservation.id.in_(observation_ids)
            )
        )
    ).scalars().all()
    return len(set(rights_profile_ids))


async def _fx_rate_reply(session: AsyncSession) -> ResearchAnswer:
    """GBP/USD only, deliberately - the one pair with a real second source
    (see _FX_PATTERN's own comment). Rights-gated on frankfurter.fx, the
    primary source in FX_SPOT_RATE_POLICY.ordered_source_codes - same
    "gate on the primary source" convention _gilt_facts_reply already uses
    for its own primary reference-terms row.
    """
    if not await _display_allowed(session, "frankfurter.fx"):
        return _default_reply("GBP/USD exchange rate")

    now = dt.datetime.now(dt.UTC)
    subject_id = fx_pair_subject_id("GBP", "USD")
    fact = await latest_accepted_fact(session, subject_id=subject_id, metric_id=METRIC_FX_SPOT_RATE)
    if fact is None:
        return _default_reply("GBP/USD exchange rate")

    assert fact.knowledge_range.lower is not None  # our own rows always set this
    knowledge_time = fact.knowledge_range.lower
    rate = Decimal(fact.value["rate"])
    source_count = await _confirming_source_count(session, fact.id) or 1

    rows = [
        ("Currency pair", f"{fact.value['base_currency']}/{fact.value['quote_currency']}"),
        ("Spot rate", f"{rate:.4f}"),
        ("Confirmed by", f"{source_count} independent source{'s' if source_count != 1 else ''}"),
    ]

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=now, status="ASSEMBLING"
    )
    session.add(bundle)
    await session.flush()
    session.add(EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=fact.id))

    label = (
        "Frankfurter (ECB-blended) + Bank of England"
        if source_count > 1
        else "Frankfurter — ECB-blended exchange rates"
    )
    return ResearchAnswer(
        text=(
            f"GBP/USD spot rate: {rate:.4f}, confirmed by {source_count} independent "
            f"source{'s' if source_count != 1 else ''}."
        ),
        facts=FactTable(title="GBP/USD exchange rate", rows=rows),
        citations=[
            Citation(
                label=label,
                meta=f"As of {knowledge_time.isoformat()}",
                pill=compute_freshness(
                    metric_id=METRIC_FX_SPOT_RATE, knowledge_time=knowledge_time, now=now
                ),
                kind="link",
            )
        ],
        note=None,
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


async def _match_equity_instrument(
    session: AsyncSession, query_text: str
) -> tuple[Instrument, str] | None:
    """Deterministic containment only (DATA-002: no fuzzy identity
    matching), same doctrine _gilt_facts_reply's own name/ISIN matching
    follows - checks every real onboarded equity's ticker or issuer's
    first word (e.g. "Apple" from "Apple Inc.") for a whole-word match in
    the query text, never a similarity/embedding match. Returns None for
    zero or ambiguous (>1) matches - an ambiguous mention is a disambig-
    uation case not yet built for equities, not something to guess at.

    The ticker check is case-SENSITIVE (issuer-name words stay case-
    insensitive) - a real, plausible collision found while building this:
    "BP" is also common finance jargon for "basis points" ("what's 10 bp
    mean"), and a case-insensitive match would route that straight into a
    BP stock-price reply. Real tickers are conventionally typed in caps
    ("BP", "AAPL"); jargon isn't, so requiring exact case filters out the
    jargon case without losing genuine ticker mentions.
    """
    rows = (
        await session.execute(
            select(Instrument, InstrumentAlias.alias_value, Issuer.name)
            .join(InstrumentAlias, InstrumentAlias.instrument_id == Instrument.id)
            .join(Issuer, Issuer.id == Instrument.issuer_id)
            .where(
                InstrumentAlias.alias_type == "TICKER",
                Instrument.instrument_type == "EQUITY_COMMON",
            )
        )
    ).all()

    matches: list[tuple[Instrument, str]] = []
    for instrument, alias_value, issuer_name in rows:
        symbol = alias_value.split(":")[-1]
        issuer_first_word = issuer_name.split()[0]
        # "BP p.l.c." starts with its own ticker ("BP") - the exact-case
        # requirement has to apply to this path too, not just the ticker
        # check above, or the same jargon collision reopens through here.
        issuer_word_needs_exact_case = issuer_first_word.upper() == symbol.upper()
        issuer_flags = 0 if issuer_word_needs_exact_case else re.I
        if re.search(rf"\b{re.escape(symbol)}\b", query_text) or re.search(
            rf"\b{re.escape(issuer_first_word)}\b", query_text, issuer_flags
        ):
            matches.append((instrument, alias_value))

    if len(matches) == 1:
        return matches[0]
    return None


async def _equity_price_reply(session: AsyncSession, query_text: str) -> ResearchAnswer | None:
    """Returns None (never a reply) when the query doesn't deterministically
    match exactly one onboarded equity - the caller falls through to the
    next intent branch rather than treating "no company mentioned" as a
    data gap worth a NEUTRAL_EDUCATION reply of its own.
    """
    match = await _match_equity_instrument(session, query_text)
    if match is None:
        return None
    instrument, alias_value = match

    if not await _display_allowed(session, "twelve-data.equity"):
        return _default_reply(f"{instrument.name} share price")

    now = dt.datetime.now(dt.UTC)
    fact = await latest_accepted_fact(
        session, subject_id=instrument.id, metric_id=METRIC_EQUITY_EOD_PRICE
    )
    if fact is None:
        return _default_reply(f"{instrument.name} share price")

    assert fact.knowledge_range.lower is not None  # our own rows always set this
    knowledge_time = fact.knowledge_range.lower
    close_price = fact.value["close_price"]
    currency_code = fact.value["currency_code"]

    rows = [
        ("Instrument", instrument.name),
        ("Ticker", alias_value),
        ("Close price", f"{close_price} {currency_code}"),
    ]

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=now, status="ASSEMBLING"
    )
    session.add(bundle)
    await session.flush()
    session.add(EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=fact.id))

    return ResearchAnswer(
        text=f"{instrument.name} ({alias_value}) closed at {close_price} {currency_code}.",
        facts=FactTable(title=f"{instrument.name} — end-of-day price", rows=rows),
        citations=[
            Citation(
                label="Twelve Data — end-of-day equity price",
                meta=f"As of {knowledge_time.isoformat()}",
                pill=compute_freshness(
                    metric_id=METRIC_EQUITY_EOD_PRICE, knowledge_time=knowledge_time, now=now
                ),
                kind="link",
            )
        ],
        note=None,
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


_MACRO_INDICATOR_LABELS: dict[str, str] = {
    "MACRO_GDP": "GDP (current US$)",
    "MACRO_CPI": "Inflation, consumer prices (annual %)",
}
_MACRO_COUNTRY_LABELS: dict[str, str] = {"GBR": "United Kingdom", "USA": "United States"}


def _format_macro_value(metric_id: str, raw_value: str) -> str:
    value = Decimal(raw_value)
    if metric_id == "MACRO_CPI":
        return f"{value:.2f}%"
    return f"${value:,.0f}"


async def _macro_reply(session: AsyncSession, metric_id: str, country: str) -> ResearchAnswer:
    """WB/WDI series only, via DBnomics - the same (provider, dataset,
    series) triple scripts._connector_registry.MACRO_PILOT_SERIES actually
    ingests, so macro_series_subject_id here must derive the identical
    subject_id that pipeline wrote facts under.
    """
    if not await _display_allowed(session, "dbnomics.macro"):
        return _default_reply(f"{_MACRO_INDICATOR_LABELS[metric_id]} — {country}")

    series_code = _MACRO_SERIES_CODES[(metric_id, country)]
    now = dt.datetime.now(dt.UTC)
    subject_id = macro_series_subject_id("WB", "WDI", series_code)
    fact = await latest_accepted_fact(session, subject_id=subject_id, metric_id=metric_id)
    if fact is None:
        return _default_reply(f"{_MACRO_INDICATOR_LABELS[metric_id]} — {country}")

    assert fact.knowledge_range.lower is not None  # our own rows always set this
    knowledge_time = fact.knowledge_range.lower
    indicator_label = _MACRO_INDICATOR_LABELS[metric_id]
    country_label = _MACRO_COUNTRY_LABELS[country]
    formatted_value = _format_macro_value(metric_id, fact.value["value"])

    rows = [
        ("Country", country_label),
        ("Indicator", indicator_label),
        ("Period", fact.value["period"]),
        ("Value", formatted_value),
    ]

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=now, status="ASSEMBLING"
    )
    session.add(bundle)
    await session.flush()
    session.add(EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=fact.id))

    return ResearchAnswer(
        text=(
            f"{country_label} {indicator_label}, {fact.value['period']}: {formatted_value}."
        ),
        facts=FactTable(title=f"{country_label} — {indicator_label}", rows=rows),
        citations=[
            Citation(
                label="World Bank — World Development Indicators (via DBnomics)",
                meta=f"As of {knowledge_time.isoformat()}",
                pill=compute_freshness(metric_id=metric_id, knowledge_time=knowledge_time, now=now),
                kind="link",
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
        jurisdiction_code=DEV_JURISDICTION,
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
    http: httpx.AsyncClient | None = None,
) -> ResearchAnswer:
    """`http` is optional and only used by the catch-all document-search
    fallback (semantic search needs an outbound call to Gemini) - every
    other branch works identically without it, and passing None just
    means the fallback degrades to lexical-only search, never an error.
    """
    if _is_advice(query_text):
        answer = _advice_reply()
    elif _is_greeting(query_text):
        answer = _greeting_reply()
    elif _is_closing(query_text):
        answer = _closing_reply()
    elif _is_help_request(query_text):
        answer = _help_reply()
    elif _mentions_accrued(query_text):
        answer = await _document_backed_accrued_reply(session) or _accrued_reply()
    elif _mentions_yield_curve(query_text):
        answer = await _yield_curve_reply(session)
    elif _mentions_fx(query_text):
        answer = await _fx_rate_reply(session)
    elif (macro_match := _mentioned_macro_series(query_text)) is not None:
        answer = await _macro_reply(session, *macro_match)
    elif (equity_answer := await _equity_price_reply(session, query_text)) is not None:
        answer = equity_answer
    elif _mentions_market_structure(query_text):
        # Checked before _mentions_gilt - see _MARKET_STRUCTURE_PATTERN's
        # own comment for the real "Gilt-Edged Market Maker" misroute
        # this guards against.
        answer = (
            await _document_backed_fallback_reply(session, query_text, http)
            or _default_reply(query_text)
        )
    elif _mentions_gilt(query_text):
        answer = await _gilt_facts_reply(session, query_text)
    else:
        answer = (
            await _document_backed_fallback_reply(session, query_text, http)
            or _default_reply(query_text)
        )

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
    # DOCUMENT_SPAN only - a fact/calculation item is self-describing via
    # metric_id/value, but a document excerpt needs its own source title
    # and text to be renderable at all (see _resolve_bundle_items).
    document_title: str | None = None
    text: str | None = None


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


async def _resolve_document_span_item(
    session: AsyncSession, document_chunk_id: uuid.UUID
) -> EvidenceItem | None:
    """DOCUMENT_SPAN rendering - a document excerpt has no metric_id/value
    to be self-describing with, so its document title (+ page, when known)
    stands in for that, and the chunk's own text is what a reader (or an
    AI Gateway prompt) actually needs. Returns None if the chunk or its
    document chain can't be resolved - never a placeholder item, matching
    _assemble_chunk_evidence's own "degrade to no citation, never a
    guessed one" rule.
    """
    chunk = await session.get(DocumentChunk, document_chunk_id)
    if chunk is None:
        return None
    parsed = await session.get(ParsedDocumentVersion, chunk.parsed_document_version_id)
    version = await session.get(DocumentVersion, parsed.document_version_id) if parsed else None
    document = await session.get(Document, version.document_id) if version else None
    if document is None:
        return None

    title = f"{document.title}, page {chunk.page_start}" if chunk.page_start else document.title
    return EvidenceItem(
        kind="DOCUMENT_SPAN",
        subject_type=None,
        metric_id=None,
        value=None,
        basis=None,
        as_of=None,
        document_title=title,
        text=chunk.text_content,
    )


async def _resolve_bundle_items(
    session: AsyncSession, bundle_id: uuid.UUID
) -> list[EvidenceItem]:
    """FACT/CALCULATION/DOCUMENT_SPAN rendering shared by every bundle
    reader - keyed on bundle_id, not research_message_id, so a bundle can
    be read before (or without ever) being attached to a persisted
    message.
    """
    members = (
        await session.execute(
            select(EvidenceMember).where(EvidenceMember.evidence_bundle_id == bundle_id)
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
        elif member.kind == "DOCUMENT_SPAN" and member.document_chunk_id is not None:
            item = await _resolve_document_span_item(session, member.document_chunk_id)
            if item is not None:
                items.append(item)
    return items


async def get_evidence_bundle_items(
    session: AsyncSession, *, bundle_id: uuid.UUID
) -> list[EvidenceItem] | None:
    """Public read accessor for other modules (ai_gateway A1's grounding
    path) that need a bundle's resolved items directly by bundle_id - a
    bundle can be Gateway input before, or without ever, being linked to a
    persisted research message. None means no such bundle exists; an empty
    list means it exists but has no renderable items - callers must treat
    those differently (the latter is a real bundle with nothing usable in
    it, the former is a bad reference).
    """
    bundle = await session.get(EvidenceBundle, bundle_id)
    if bundle is None:
        return None
    return await _resolve_bundle_items(session, bundle_id)


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

    items = await _resolve_bundle_items(session, bundle.id)

    return EvidenceDetail(
        evidence_bundle_id=bundle.id,
        purpose_type=bundle.purpose_type,
        status=bundle.status,
        items=items,
    )
