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
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.calculation.models import (
    CalculationInput,
    CalculationResult,
    CalculationSpecification,
)
from app.modules.calculation.pipeline.curve_pricing import METRIC_MODEL_IMPLIED_CLEAN_PRICE
from app.modules.calculation.pipeline.gilt_holding_period_return_pricing import (
    HoldingPeriodReturnComputed,
    compute_and_persist_holding_period_return,
)
from app.modules.calculation.pipeline.gilt_risk_metrics_pricing import METRIC_GILT_RISK_METRICS
from app.modules.calculation.pipeline.gilt_treasury_spread_pricing import (
    SpreadComputed,
    compute_and_persist_gilt_treasury_spread,
)
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
from app.modules.market.change_detection import DetectedChange, NoChangeDetected, detect_change
from app.modules.market.freshness import compute_freshness
from app.modules.market.models import (
    AcceptedFact,
    Dataset,
    FactObservationLink,
    Source,
    SourceArtifact,
    SourceObservation,
)
from app.modules.market.pipeline.curve_ingest import (
    METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
    SUBJECT_TYPE_YIELD_CURVE_POINT,
    curve_point_subject_id,
)
from app.modules.market.pipeline.equity_ingest import METRIC_EQUITY_EOD_PRICE
from app.modules.market.pipeline.fx_ingest import METRIC_FX_SPOT_RATE, fx_pair_subject_id
from app.modules.market.pipeline.identity_resolution import (
    ResolvedIdentity,
    UnresolvedIdentity,
    resolve_instrument_by_isin,
)
from app.modules.market.pipeline.macro_ingest import macro_series_subject_id
from app.modules.market.pipeline.stages import METRIC_GILT_REFERENCE_TERMS
from app.modules.market.pipeline.tradeweb_price_ingest import METRIC_GILT_MARKET_CLOSE_PRICE
from app.modules.market.pipeline.treasury_curve_ingest import (
    METRIC_US_TREASURY_PAR_YIELD_CURVE,
    SUBJECT_TYPE_TREASURY_CURVE_POINT,
    treasury_curve_point_subject_id,
)
from app.modules.market.queries import (
    accepted_fact_as_of,
    current_accepted_fact_at,
    latest_accepted_fact,
)
from app.modules.policy.allowed_output_type import AllowedOutputType
from app.modules.policy.pdp import PolicyContext, evaluate
from app.modules.reference.models import Instrument, InstrumentAlias, Issuer
from app.modules.rights.engine import RightsAction, RightsDecision, evaluate_action
from app.modules.rights.models import RightsProfile

DEV_JURISDICTION = "GB"
RESEARCH_CAPABILITY_CODE = "research.answer"
SEED_GILT_ISIN = "GB0032452392"

_ADVICE_PATTERNS = [
    re.compile(r"should i (buy|sell|invest|hold)", re.I),
    re.compile(r"\b(is|are) (it|this|these|that) a good (buy|investment|idea)\b", re.I),
    re.compile(
        r"\b(is|are) (it|this|these|that) (risky|safe|worth it|advisable)\b.*?\b(to buy|to invest|to hold|buying|investing)?\b",
        re.I,
    ),
    re.compile(r"\b(risk|risky|safe)\b.*?\b(to buy|to invest|buying|investing)\b", re.I),
    re.compile(r"what should i (buy|invest|pick)", re.I),
    re.compile(
        r"\b(best|top|worst) (bond|gilt|treasury|pick|investment|crypto|coin|stock)s?\b", re.I
    ),
    re.compile(r"\b(price target|fair value|rating|recommend(?:ations?|ing|s)?)\b", re.I),
    re.compile(r"worth (buying|investing)", re.I),
    re.compile(
        r"\b(rank|ranking|ranked)\b[^.?!]{0,60}"
        r"\b(bond|gilt|treasury|pick|investment|instrument|stock|equity|security|crypto|coin)s?\b",
        re.I,
    ),
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
# A bare ISIN is already the deterministic instrument identifier the rest
# of the platform resolves by (DATA-002 exact alias match, never fuzzy),
# but until now nothing ROUTED on it: "Tell me about GB0032452392"
# mentioned no keyword any branch recognised and fell through to the
# document-search catch-all, and "what is the price of GB00BNNGP668?"
# answered from an unrelated corpus excerpt instead of either the
# instrument's own facts or an honest "not in our reference data" (both
# found live 2026-10-15, finding F2). This is a pattern only - actual
# resolution still goes through resolve_instrument_by_isin's exact alias
# lookup; a token that merely looks like an ISIN but isn't registered gets
# an honest unresolved reply, never a guessed instrument.
#
# Shape: 2-letter country prefix + 9 alphanumerics + 1 check digit (12
# chars total). The check digit is deliberately NOT verified here - the
# exact alias lookup already decides whether the platform knows the ISIN,
# and requiring a valid checksum would only send a mistyped-but-genuinely-
# asked-about ISIN back to the document catch-all, which is the F2 bug
# this replaces.
_ISIN_PATTERN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b", re.I)
# Checked BEFORE _GILT_PATTERN below - "Gilt-Edged Market Maker" contains
# the substring "gilt", so without this a genuine market-structure/dealer
# question was silently misrouted to the single-instrument facts branch
# (found live, 2026-09-23, asking about GEMM obligations after the GEMM
# Guidebook was added to the document corpus - it never reached the
# document search that would have actually answered it). This pattern
# doesn't try to be a general topic classifier, just to catch the one
# real ambiguity "gilt" as a substring creates against this specific
# document's own subject matter.
#
# The bare "\bdmo\b" alternative was added later (found live, 2026-10-15,
# 100-query sweep): "what is the DMO?" matched no branch at all and fell to
# the generic catch-all's "doesn't yet have reconciled data" reply, while
# the original "dmo.*(role|obligation)" only caught DMO questions that also
# named a role - the simplest possible question about the issuer didn't
# qualify. The negative lookahead keeps the new alternative scoped to
# questions ABOUT the DMO: a DMO that is merely qualifying an instrument or
# data noun ("DMO gilt closing prices", "DMO auction results") is a request
# for gilt data, and must keep reaching the gilt-facts branch below.
_MARKET_STRUCTURE_PATTERN = re.compile(
    r"market maker|\bgemm\b|primary dealer|going live|\bdmo\b.*(role|obligation)"
    r"|\bdmo\b(?!\s*['\u2019]?s?\s*(?:gilt|bond|treasury|price|yield|auction|"
    r"issuance|closing|data|report|results|calendar|timetable))",
    re.I,
)
_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
#: Document-corpus questions that merely CONTAIN the word "gilt" were
#: captured by the gilt-facts branch before the document search ever saw
#: them (found live 2026-10-15, finding F12: "how does the DMO issue
#: gilts?" came back as the deterministic instrument-facts text rather
#: than a document answer). The gilt-facts branch can only ever render one
#: instrument's data table - it cannot answer a "how/why" mechanism
#: question at all. _prefers_document_explanation below admits exactly the
#: explanation-framed questions for which that table is never an answer,
#: and only when nothing more specific was named: no maturity year (that
#: identifies a gilt the facts branch resolves), no ISIN (same), and no
#: explicit data-request term like "price" or "yield" (those ARE facts-
#: branch questions even when phrased "how"/"why", e.g. "why is the gilt
#: price falling?").
_DOCUMENT_EXPLANATION_PATTERN = re.compile(
    r"^\s*(?:how|why)\b"
    r"|^\s*(?:explain|describe|walk me through|tell me why|what makes|what causes|what happens)\b",
    re.I,
)
_GILT_DATA_TERM_PATTERN = re.compile(
    r"\bprices?\b|\byields?\b|\bcoupons?\b|\bmaturit|\bredemption\b"
    r"|\bclosings?\b|\bquotes?\b|\bdurations?\b|\bdv01\b|\bspreads?\b|\bcost\b",
    re.I,
)


def _prefers_document_explanation(text: str) -> bool:
    if _YEAR_PATTERN.search(text) or _ISIN_PATTERN.search(text):
        return False
    if _GILT_DATA_TERM_PATTERN.search(text):
        return False
    return bool(_DOCUMENT_EXPLANATION_PATTERN.search(text))
_ACCRUED_PATTERN = re.compile(
    r"accrued|day count|convention|clean|dirty|act/act|ex[- ]?dividend", re.I
)
# Deliberately no bare "yield": "what is the yield of the 2036 gilt?" is
# the gilt-facts branch's question and "explain redemption yield
# calculation" is the document corpus's, and neither may be stolen. But a
# *gilt yield* phrasing has no branch that can answer it (found live,
# 2026-10-15): "what is the 10 year gilt yield?" matched neither this
# pattern nor a year, so _GILT_PATTERN caught it - and the single-instrument
# branch then replied that a 10-year yield "cannot be determined" while
# this same platform held 10Y = 5.3613% in the curve branch it never
# reached. Hence two additions, both unambiguously asking for a curve
# point: "gilt yield(s)" as a unit, and a tenor immediately ahead of
# "yield".
_YIELD_CURVE_PATTERN = re.compile(
    r"yield curve|spot curve|interest rates?\b|bank of england|\bboe\b"
    r"|\bgilt yields?\b"
    r"|\b\d{1,3}\s*[- ]?\s*years?\b[^.?!]{0,40}\byields?\b",
    re.I,
)
# Requires either the unambiguous phrase "exchange rate", or BOTH a
# GBP-side and a USD-side term (either order) - never a single currency
# word alone, which would false-positive on "the dollar cost of..." or
# similar. Only one pair is actually cross-source reconciled today
# (GBP/USD, frankfurter + boe - see reconciliation_policy.FX_SPOT_RATE_
# POLICY), so this deliberately doesn't try to parse an arbitrary pair out
# of free text; _fx_rate_reply always answers with that one canonical pair.
# The "GBPUSD" ticker spelling needs its own alternative: neither currency
# word has a word boundary against the other, so the paired-term rules
# above never fire on it ("GBPUSD spot rate" returned "no reconciled data"
# while "GBP/USD" answered - found live, 2026-10-15, 100-query sweep).
_GBP_TERMS = r"\bgbp\b|\bpound\b|\bpounds\b|\bsterling\b"
_USD_TERMS = r"\busd\b|\bdollar\b|\bdollars\b"
_FX_PATTERN = re.compile(
    rf"exchange rate|\bgbpusd\b|\busdgbp\b"
    rf"|(?:{_GBP_TERMS}).*(?:{_USD_TERMS})|(?:{_USD_TERMS}).*(?:{_GBP_TERMS})",
    re.I,
)
# Requires BOTH a metric term (GDP or CPI/inflation) AND a country term -
# only UK/USA are in scope (see memory: an earlier India/NSE equity list
# was a real, flagged scope inconsistency; MACRO_PILOT_SERIES in scripts/
# _connector_registry.py still has 2 India series too, same kind of
# pre-existing leftover, left alone here since nothing routes to them).
# Deliberately no bare "\bus\b" - "us" as a pronoun ("tell us about...")
# would false-positive constantly; "usa"/"united states"/"america" are
# unambiguous instead. That exclusion cost something real (found live,
# 2026-10-15): "US GDP" matched a metric term but no country term and fell
# through to "doesn't yet have reconciled data", while "America GDP"
# answered correctly - the most common way of asking for US macro data
# returned a refusal. Two narrow ways back in, neither of which can catch
# the pronoun: the UPPERCASE form wherever it appears (a lowercased "us"
# is far more likely to be the pronoun), and lower/mixed-case "us" only
# when a metric term follows it immediately - "tell us about..." never
# runs "us gdp".
_MACRO_METRIC_TERMS: dict[str, str] = {
    "MACRO_GDP": r"\bgdp\b|gross domestic product",
    "MACRO_CPI": r"\bcpi\b|inflation|consumer price",
}
_MACRO_COUNTRY_TERMS: dict[str, str] = {
    "GBR": r"\buk\b|united kingdom|\bbritain\b|\bbritish\b",
    "USA": (
        r"\busa\b|united states|\bamerica\b|american"
        r"|\b(?-i:US)\b"
        r"|\bus\b(?=\s+(?:gdp|cpi|inflation|consumer price|gross domestic))"
    ),
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
#
# "how can you help me" is the same topic-less ask in a different shape
# (found live, 2026-10-15, 100-query sweep - it fell to "no reconciled
# data" while "what can you do?" answered). It is end-anchored on purpose:
# that keeps "...help me understand accrued interest" out, so the guard
# above still holds for a real data question phrased with "help me".
_HELP_PATTERN = re.compile(
    r"which topics|what topics|what (can|do) (you|u) (do|answer|cover|know)|"
    r"help with\b|what (are|is) your capabilit|"
    r"how (can|do) (you|u) help( me| us)?\s*\??\s*$",
    re.I,
)
# Whole-message match only (never a substring search like the other intent
# patterns) - "hi" as a real word inside an actual question ("this hi-yield
# bond...") must never be mis-routed here. A bare greeting is treated as an
# implicit "what can you help with" - the same honest capability list a
# generic "no data" reply would otherwise cold-open with.
_GREETING_PATTERN = re.compile(
    r"^\s*(hi|hello|hey|hiya|yo|greetings|good (morning|afternoon|evening))( there)?"
    r"\s*[!.]?\s*$",
    re.I,
)
# Same whole-message-only reasoning as _GREETING_PATTERN - "thanks" as a
# real word inside an actual question must never be mis-routed here. Before
# this existed, "thank you" fell all the way through to the cold, generic
# _default_reply ("doesn't yet have reconciled data covering this
# question") - technically correct (no document matches "thank you") but
# an unfriendly, un-conversational answer to what is obviously a closing
# remark, not a data question.
#
# The original shape was one whole-message regex of a handful of stock
# phrases, and live testing found the gaps that costs: "Thanks, that's all"
# and "hello, thanks" both fell through to the generic reply (finding F1,
# 2026-10-15) because neither is any single listed phrase. A closing is
# now recognised as a short message BUILT from closing parts, split on
# conversational separators: every part must be a greeting/closing word,
# and at least one part must carry the actual closing (a modifier like
# "ok" alone is not one - "ok" on its own is an acknowledgement, not a
# farewell). Still whole-message: "thanks to the ex-dividend convention,
# what is accrued interest" has a non-closing part and must never be
# mis-routed here.
_CLOSING_PRIMARY_PART = (
    r"thanks?(?: you)?(?: (?:very|so) much)?(?: a (?:lot|ton))?"
    r"|cheers"
    r"|(?:i )?appreciate(?: it)?|much appreciated"
    r"|bye(?: bye)?|goodbye|good night"
    r"|see you(?: later| soon| tomorrow)?"
    r"|that(?:'?s| is|was) all(?: for (?:now|today))?"
    r"|nothing else(?: for now)?"
    r"|(?:i'?m|we'?re|we are|all) (?:done|finished)"
)
_CLOSING_MODIFIER_PART = (
    r"ok(?:ay)?|great|perfect|lovely|nice|well|right"
    r"|hi|hello|hey|hiya|yo|greetings|good (?:morning|afternoon|evening)"
)
_CLOSING_SEPARATOR = re.compile(r"\s*(?:,|;|&|\band\b|\u2014)\s*", re.I)
# NB the extra (?:...) around each part - an alternation binds looser than
# concatenation, so `{_CLOSING_MODIFIER_PART}\s+` unparenthesised would
# attach the \s+ only to the last alternative ("ok thanks" would never
# match, which the integration suite caught).
_CLOSING_PRIMARY_RE = re.compile(
    rf"^\s*(?:(?:{_CLOSING_MODIFIER_PART})\s+)*(?:{_CLOSING_PRIMARY_PART})"
    rf"(?:\s+(?:{_CLOSING_MODIFIER_PART}))*\s*$",
    re.I,
)
_CLOSING_MODIFIER_RE = re.compile(rf"^\s*(?:(?:{_CLOSING_MODIFIER_PART})\s*)+$", re.I)


def _is_advice(text: str) -> bool:
    return any(p.search(text) for p in _ADVICE_PATTERNS)


def _is_help_request(text: str) -> bool:
    return bool(_HELP_PATTERN.search(text))


def _is_greeting(text: str) -> bool:
    return bool(_GREETING_PATTERN.match(text))


def _is_closing(text: str) -> bool:
    message = re.sub(r"[.!]+$", "", text.strip())
    if not message:
        return False
    parts = [part for part in _CLOSING_SEPARATOR.split(message) if part.strip()]
    if not parts:
        return False
    return any(_CLOSING_PRIMARY_RE.match(part) for part in parts) and all(
        _CLOSING_PRIMARY_RE.match(part) or _CLOSING_MODIFIER_RE.match(part) for part in parts
    )


def _mentions_gilt(text: str) -> bool:
    return bool(_GILT_PATTERN.search(text))


def _mentioned_isin(text: str) -> str | None:
    """The first ISIN-shaped token, upper-cased (ISINs are conventionally
    written in capitals, but a user may type one lowercase - the alias
    registry stores them uppercase, so the comparison key must be too).
    """
    match = _ISIN_PATTERN.search(text)
    return match.group().upper() if match else None


def _mentions_market_structure(text: str) -> bool:
    return bool(_MARKET_STRUCTURE_PATTERN.search(text))


def _mentioned_year(text: str) -> int | None:
    match = _YEAR_PATTERN.search(text)
    return int(match.group()) if match else None


def _mentions_yield_curve(text: str) -> bool:
    return bool(_YIELD_CURVE_PATTERN.search(text))


_TREASURY_PATTERN = re.compile(
    r"\bus\s*treasur(?:y|ies)\b|\btreasury\s*(?:yield|note|bill|bond)s?\b"
    r"|\bus10y\b|\b10y\b|\bus\s*10[- ]?year\b|\bt-note\b|\bconstant maturity\b",
    re.I,
)


def _mentions_treasury(text: str) -> bool:
    lower = text.lower()
    if (
        "gilt" in lower
        or "glit" in lower
        or "treasury stock" in lower
        or "treasury gilt" in lower
        or _mentions_gilt(text)
    ):
        return False
    return bool(_TREASURY_PATTERN.search(text))


def _mentions_fx(text: str) -> bool:
    return bool(_FX_PATTERN.search(text))


_CRYPTO_PATTERN = re.compile(
    r"\b(?:crypto|cryptocurrency|cryptocurrencies|coinmarketcap|cmc)\b"
    r"|\b(?:bitcoin|btc|ethereum|eth|solana|sol|binance\s*coin|bnb|ripple|xrp"
    r"|cardano|ada|doge|dogecoin|avalanche|avax|chainlink|link|polkadot|dot"
    r"|near\s*protocol|sui|uniswap|uni|toncoin|ton|polygon|matic|pol|litecoin|ltc)\b",
    re.I,
)


def _mentions_crypto(text: str) -> bool:
    return bool(_CRYPTO_PATTERN.search(text))


_COMMODITY_PATTERN = re.compile(
    r"\b(?:commodity|commodities|lbma|cme|nymex|comex)\b"
    r"|\b(?:gold|xau|xauusd|silver|xag|xagusd|crude\s*oil|brent|wti"
    r"|natural\s*gas|natgas|copper|platinum|xpt)\b",
    re.I,
)


def _mentions_commodity(text: str) -> bool:
    return bool(_COMMODITY_PATTERN.search(text))


_GLOBAL_INDEX_PATTERN = re.compile(
    r"\b(?:s&p\s*500|spx|s&p500|nasdaq|ndx|dow\s*jones|djia|russell\s*2000"
    r"|ftse\s*100|dax|dax\s*40|cac\s*40|euro\s*stoxx|stoxx\s*50|nikkei|nikkei\s*225"
    r"|hang\s*seng|nifty|nifty\s*50|sensex|bse\s*sensex|tradingview)\b",
    re.I,
)


def _mentions_global_index(text: str) -> bool:
    return bool(_GLOBAL_INDEX_PATTERN.search(text))


_IPO_PATTERN = re.compile(
    r"\b(?:ipo|ipos|initial\s*public\s*offering|drhp|red\s*herring|prospectus|listing\s*date|issue\s*size|price\s*band|grey\s*market|gmp|anchor\s*investor)\b"
    r"|\b(?:jio\s*ipo|swiggy\s*ipo|hyundai\s*ipo|tata\s*ipo|stripe\s*ipo|reddit\s*ipo|ola\s*ipo)\b",
    re.I,
)


def _mentions_ipo(text: str) -> bool:
    return bool(_IPO_PATTERN.search(text))


_MUTUAL_FUND_PATTERN = re.compile(
    r"\b(?:mutual\s*fund|mutual\s*funds|nav|net\s*asset\s*value|expense\s*ratio|amc|amfi|aum|sip|systematic\s*investment)\b"
    r"|\b(?:vanguard\s*fund|blackrock\s*fund|fidelity\s*fund|sbi\s*mutual|hdfc\s*mutual|parag\s*parikh|nippon\s*india|mirae\s*asset|uti\s*mutual|icici\s*prudential)\b",
    re.I,
)


def _mentions_mutual_fund(text: str) -> bool:
    return bool(_MUTUAL_FUND_PATTERN.search(text))


_ETF_PATTERN = re.compile(
    r"\b(?:etf|etfs|exchange-traded\s*fund|exchange\s*traded\s*fund|index\s*fund|vanguard|ishares|spdr|invesco)\b"
    r"|\b(?:spy|qqq|voo|vti|iwm|dia|tlt|ief|shy|bnd|agg|lqd|hyg|gld|slv|uso|ung|smh|xlk|xlf|xle|xlv|arkk|eem|inda)\b",
    re.I,
)


def _mentions_etf(text: str) -> bool:
    return bool(_ETF_PATTERN.search(text))


_DEEP_EQUITY_PATTERN = re.compile(
    r"\b(?:deep\s*research|fundamental\s*research|equity\s*research|valuation|financials|balance\s*sheet|income\s*statement|p/e\s*ratio|market\s*cap|free\s*cash\s*flow)\b"
    r"|\b(?:nvda|nvidia|aapl|apple|msft|microsoft|googl|goog|alphabet|amzn|amazon|meta|tsla|tesla|asml|tsm|tsmc|arm|avgo|broadcom|lly|eli\s*lilly|nvo|novo\s*nordisk|berkshire|jpm|jpmorgan|visa|azn|astrazeneca|shel|shell|hsba|hsbc|sap|lvmh|toyota|reliance|tcs|infy|infosys|hdfc|hdfcbank)\b",
    re.I,
)


def _mentions_deep_equity(text: str) -> bool:
    return bool(_DEEP_EQUITY_PATTERN.search(text))


#: Only unambiguous month-name date forms, never bare numeric ones
#: ("15/09/2026") — DD/MM vs MM/DD is genuinely ambiguous between UK and
#: US convention on this platform, and DATA-002's "never guess" doctrine
#: applies just as much to parsing a date as to resolving an identity: an
#: unparseable date must fall through honestly, never be silently
#: misread as the wrong day.
_MONTH_NAMES: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH_YEAR_PATTERN = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})\b")
_MONTH_DAY_YEAR_PATTERN = re.compile(
    r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"
)
_HISTORICAL_TRIGGER_PATTERN = re.compile(
    r"\bwhat did (?:talvrin|you) know\b|\bwhat was known\b|\bas of\b|\bas at\b"
    r"|\bback on\b|\bhistorically\b|\bused to (?:be|show)\b",
    re.I,
)

_CHANGE_TRIGGER_PATTERN = re.compile(
    r"\bwhat(?:'?s| is| has) changed\b|\bwhat changed\b|\bany changes?\b"
    r"|\bhas .+ changed\b|\brecent changes?\b|\bmaterial changes?\b"
    r"|\bwhat'?s new\b|\bchanges? to\b",
    re.I,
)


def _mentions_change_query(text: str) -> bool:
    return bool(_CHANGE_TRIGGER_PATTERN.search(text))


def _parse_mentioned_date(text: str) -> dt.date | None:
    iso = _ISO_DATE_PATTERN.search(text)
    if iso is not None:
        try:
            return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    dmy = _DAY_MONTH_YEAR_PATTERN.search(text)
    if dmy is not None:
        month = _MONTH_NAMES.get(dmy.group(2).lower())
        if month is not None:
            try:
                return dt.date(int(dmy.group(3)), month, int(dmy.group(1)))
            except ValueError:
                return None

    mdy = _MONTH_DAY_YEAR_PATTERN.search(text)
    if mdy is not None:
        month = _MONTH_NAMES.get(mdy.group(1).lower())
        if month is not None:
            try:
                return dt.date(int(mdy.group(3)), month, int(mdy.group(2)))
            except ValueError:
                return None

    return None


def _mentioned_historical_cutoff(text: str) -> dt.date | None:
    """A historical cutoff is only ever recognised alongside an explicit
    trigger phrase - a query that merely happens to contain a date (e.g.
    "AZN reported results on 15 September 2026") is not a historical
    question, and routing it as one would silently hide the user's actual
    (present-tense) question behind a point-in-time reconstruction of
    something they never asked to look back at.
    """
    if not _HISTORICAL_TRIGGER_PATTERN.search(text):
        return None
    return _parse_mentioned_date(text)


_FROM_TO_DATE_PATTERN = re.compile(r"from\s+(.+?)\s+to\s+(.+?)(?:[,.?]|$)", re.I)


def _mentioned_date_range(text: str) -> tuple[dt.date, dt.date] | None:
    """Only the explicit "from <date> to <date>" phrasing - deliberately
    narrower than scanning for any two dates anywhere in the text, which
    would risk pairing two unrelated dates mentioned for other reasons.
    end_date must be strictly after start_date, or this isn't a valid
    range at all (never silently swapped).
    """
    match = _FROM_TO_DATE_PATTERN.search(text)
    if match is None:
        return None
    start = _parse_mentioned_date(match.group(1))
    end = _parse_mentioned_date(match.group(2))
    if start is None or end is None or end <= start:
        return None
    return start, end


_SPREAD_TRIGGER_PATTERN = re.compile(r"\bspread\b", re.I)
_SPREAD_TENOR_PATTERN = re.compile(r"\b(1|2|5|10|20|30)[\s-]?(?:year|yr|y)\b", re.I)


def _mentioned_spread_tenor(text: str) -> int:
    """Defaults to the 10-year point - the single most commonly quoted
    benchmark tenor in cross-market comparisons - when the question names
    no specific one (e.g. "what's the gilt-treasury spread?").
    """
    match = _SPREAD_TENOR_PATTERN.search(text)
    return int(match.group(1)) if match else 10


_HOLDING_PERIOD_RETURN_TRIGGER_PATTERN = re.compile(r"\breturn\b", re.I)


def _mentions_holding_period_return(text: str) -> bool:
    return bool(
        _HOLDING_PERIOD_RETURN_TRIGGER_PATTERN.search(text)
    ) and _mentioned_date_range(text) is not None


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


#: Gilt coupons are written three equivalent ways in real questions: the
#: canonical single-character vulgar fraction ("4\u00bc% Treasury Stock
#: 2036"), an ASCII mixed fraction ("4 1/4%"), and a decimal ("4.25%").
#: They are the same deterministic number, but the ambiguous-year narrowing
#: in _gilt_facts_reply is an exact-substring test against the canonical
#: instrument_name - so "the redemption date of the 4.25% Treasury Stock
#: 2036?" fell back to the ambiguous two-gilt list even though it names one
#: gilt unambiguously (found live, 2026-10-15, 100-query sweep; the ASCII
#: "4 1/4%" form missed for the same reason). Normalising BOTH sides to a
#: decimal string keeps the test exact and deterministic (DATA-002) - only
#: two spellings of the same value compare equal, nothing else does.
_VULGAR_FRACTIONS: dict[str, str] = {
    "\u00bc": ".25",  # 1/4
    "\u00bd": ".5",  # 1/2
    "\u00be": ".75",  # 3/4
    "\u215b": ".125",  # 1/8
    "\u215c": ".375",  # 3/8
    "\u215d": ".625",  # 5/8
    "\u215e": ".875",  # 7/8
}
_MIXED_FRACTION_PATTERN = re.compile(r"\b(\d+)\s*[- ]\s*(\d+)\s*/\s*(\d+)\b")


def _normalise_coupon_text(text: str) -> str:
    """Lower-case `text` and rewrite every vulgar/ASCII fraction spelling of
    a number as its decimal form, so "4\u00bc%", "4 1/4%" and "4.25%" all
    become "4.25%" and compare equal by plain substring containment.
    """
    lowered = text.lower()
    for fraction, decimal in _VULGAR_FRACTIONS.items():
        lowered = lowered.replace(fraction, decimal)

    def _as_decimal(match: re.Match[str]) -> str:
        whole, numerator, denominator = (int(group) for group in match.groups())
        if denominator == 0:
            return match.group(0)
        return f"{whole + numerator / denominator:g}"

    return _MIXED_FRACTION_PATTERN.sub(_as_decimal, lowered)


@dataclass(frozen=True)
class Citation:
    label: str
    meta: str | None
    pill: str  # CURRENT | DELAYED | STALE | UNAVAILABLE | SOURCE - mirrors frontend's Freshness
    kind: str  # doc | book | link
    url: str | None = None


@dataclass(frozen=True)
class FactTable:
    title: str
    rows: list[tuple[str, str]]


#: The only `note` that means "this `text` is not an answer we wrote" -
#: the document fallback hands back a raw corpus excerpt rather than
#: prose the platform authored.
_RAW_EXCERPT_NOTE = (
    "A raw source excerpt, not a synthesized explanation - "
    "retrieved from the document corpus, not accepted facts or a calculation."
)


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
        purpose_type="FACTUAL_EXPLANATION",
        knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    locator = CitationLocator(
        document_chunk_id=chunk.id,
        locator_type="PAGE",
        locator_data={"page": chunk.page_start},
    )
    session.add(locator)
    await session.flush()
    session.add(
        EvidenceMember(
            evidence_bundle_id=bundle.id,
            kind="DOCUMENT_SPAN",
            document_chunk_id=chunk.id,
            citation_locator_id=locator.id,
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
                url="https://www.dmo.gov.uk/media/334d05fo/yldeqns_v4.pdf",
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

#: The Guidebook's own section heading, used as the retrieval anchor when a
#: market-structure question's real words can't clear _MIN_LEXICAL_MATCH_RANK
#: on their own. Real case found live (2026-10-15, 100-query sweep):
#: "what is the DMO?" reduces through plainto_tsquery to just 'dmo', a token
#: so common in this corpus that every match ranks ~0.097 - below the 0.15
#: bar - so the honest "we don't cover this" reply was returned even though
#: the Guidebook *is* "a guide to the roles of the DMO and Primary
#: Dealers". Semantic search doesn't rescue it either: the nearest chunk
#: sits at cosine distance 0.419, just past _MAX_SEMANTIC_MATCH_DISTANCE,
#: and is an unrelated counterparty-classification page, not a definition.
#: This heading instead ranks page 7 ("This Guidebook sets out the United
#: Kingdom Debt Management Office's (DMO) relationship with ... its primary
#: dealer firms, the GEMMs") at ts_rank 0.88.
_MARKET_STRUCTURE_ANCHOR = "gilt-edged market makers introduction"


def _looks_like_a_data_table(text: str) -> bool:
    nonspace = [ch for ch in text if not ch.isspace()]
    if not nonspace:
        return False
    digit_ratio = sum(ch.isdigit() for ch in nonspace) / len(nonspace)
    return digit_ratio > _MAX_PROSE_DIGIT_RATIO


async def _excerpt_answer(
    session: AsyncSession, query_text: str, chunk: DocumentChunk
) -> ResearchAnswer | None:
    """Render one retrieved chunk as the honest "I don't have live
    reconciled data, but <document> covers it" answer - the shared tail of
    every document-search branch, so a chunk found against the caller's own
    words and one found through a retrieval anchor render identically.
    """
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
        note=_RAW_EXCERPT_NOTE,
        allowed_output_type=AllowedOutputType.DOCUMENT_EXPLANATION,
        evidence_bundle_id=evidence.bundle_id,
    )


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
                session,
                query_text=query_text,
                http=http,
                api_key=settings.gemini_api_key,
                limit=1,
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

    return await _excerpt_answer(session, query_text, chunks[0])


async def _document_backed_market_structure_reply(
    session: AsyncSession, query_text: str, http: httpx.AsyncClient | None
) -> ResearchAnswer | None:
    """Market-structure questions are Guidebook concept questions, so they
    want the same document search - but a short one ("what is the DMO?")
    can reduce to a single, corpus-ubiquitous token that no relevance
    ordering can lift over the bar. When the caller's own words find
    nothing, re-run the lexical search against the Guidebook's own section
    heading (see _MARKET_STRUCTURE_ANCHOR) rather than returning "no data"
    about a topic the corpus demonstrably covers. The caller's real query is
    still what gets echoed back.
    """
    answer = await _document_backed_fallback_reply(session, query_text, http)
    if answer is not None:
        return answer
    chunks = await search_chunks_by_text(
        session,
        query_text=_MARKET_STRUCTURE_ANCHOR,
        limit=1,
        min_rank=_MIN_LEXICAL_MATCH_RANK,
    )
    if not chunks:
        return None
    return await _excerpt_answer(session, query_text, chunks[0])


async def _historical_yield_curve_reply(session: AsyncSession, as_of_date: dt.date) -> ResearchAnswer:
    """Reconstructs the UK nominal gilt spot curve as Talvrin held it as of
    a historical knowledge cutoff — mirrors _yield_curve_reply's shape
    exactly, but each tenor is looked up via accepted_fact_as_of instead of
    "whatever is currently ACTIVE", so a later correction never leaks into
    this answer. The market-effective date of the curve returned can be
    earlier than as_of_date itself (the BoE's own feed routinely publishes
    a day or more behind - see accepted_fact_as_of's docstring), so both
    dates are shown explicitly rather than conflated into one.
    """
    if not await _display_allowed(session, "boe.yield-curve"):
        return _default_reply(f"UK yield curve as of {as_of_date.isoformat()}")

    rows: list[tuple[str, str]] = []
    used_facts: list[AcceptedFact] = []
    for tenor, label in _BENCHMARK_TENORS:
        fact = await accepted_fact_as_of(
            session,
            subject_id=curve_point_subject_id(tenor),
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            as_of_date=as_of_date,
        )
        if fact is None:
            continue
        rows.append((label, f"{fact.value['spot_rate_pct']}%"))
        used_facts.append(fact)

    if not rows:
        return _default_reply(f"UK yield curve as of {as_of_date.isoformat()}")

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

    earliest_known = min(
        f.knowledge_range.lower for f in used_facts if f.knowledge_range.lower is not None
    )
    effective_date = max(
        f.valid_range.lower for f in used_facts if f.valid_range.lower is not None
    ).date()
    return ResearchAnswer(
        text=(
            f"As Talvrin knew by the end of {as_of_date.isoformat()}, here is the UK nominal "
            f"gilt spot curve — market-effective {effective_date.isoformat()} (first recorded "
            f"{earliest_known.date().isoformat()}), not today's current, possibly since-revised "
            f"state."
        ),
        facts=FactTable(
            title=f"UK nominal gilt spot curve as known by {as_of_date.isoformat()}", rows=rows
        ),
        citations=[
            Citation(
                label="Bank of England — daily nominal gilt spot curve (historical reconstruction)",
                meta=(
                    f"Market-effective {effective_date.isoformat()}; "
                    f"known to Talvrin by {as_of_date.isoformat()}"
                ),
                pill="SOURCE",
                kind="doc",
                url="https://www.bankofengland.co.uk/statistics/yield-curves",
            )
        ],
        note=(
            "This reconstructs a past knowledge state, not a live quote — any correction "
            "made after your requested cutoff date is deliberately not reflected here."
        ),
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


async def _historical_treasury_curve_reply(
    session: AsyncSession, as_of_date: dt.date
) -> ResearchAnswer:
    """The US Treasury equivalent of _historical_yield_curve_reply — same
    knowledge-cutoff reconstruction, same reasoning."""
    if not await _display_allowed(session, "treasury.yield-curve"):
        return _default_reply(f"US Treasury yield curve as of {as_of_date.isoformat()}")

    rows: list[tuple[str, str]] = []
    used_facts: list[AcceptedFact] = []
    for field, label in _TREASURY_BENCHMARK_TENORS:
        fact = await accepted_fact_as_of(
            session,
            subject_id=treasury_curve_point_subject_id(field),
            metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
            as_of_date=as_of_date,
        )
        if fact is None:
            continue
        rows.append((label, f"{fact.value['par_yield_pct']}%"))
        used_facts.append(fact)

    if not rows:
        return _default_reply(f"US Treasury yield curve as of {as_of_date.isoformat()}")

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

    earliest_known = min(
        f.knowledge_range.lower for f in used_facts if f.knowledge_range.lower is not None
    )
    effective_date = max(
        f.valid_range.lower for f in used_facts if f.valid_range.lower is not None
    ).date()
    return ResearchAnswer(
        text=(
            f"As Talvrin knew by the end of {as_of_date.isoformat()}, here is the US Treasury "
            f"par yield curve — market-effective {effective_date.isoformat()} (first recorded "
            f"{earliest_known.date().isoformat()}), not today's current, possibly since-revised "
            f"state."
        ),
        facts=FactTable(
            title=f"US Treasury par yield curve as known by {as_of_date.isoformat()}", rows=rows
        ),
        citations=[
            Citation(
                label=(
                    "U.S. Department of the Treasury — Daily Par Yield Curve Rates "
                    "(historical reconstruction)"
                ),
                meta=(
                    f"Market-effective {effective_date.isoformat()}; "
                    f"known to Talvrin by {as_of_date.isoformat()}"
                ),
                pill="SOURCE",
                kind="doc",
                url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/",
            )
        ],
        note=(
            "This reconstructs a past knowledge state, not a live quote — any correction "
            "made after your requested cutoff date is deliberately not reflected here."
        ),
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


async def _historical_inventory_reply(session: AsyncSession, as_of_date: dt.date) -> ResearchAnswer:
    """Bare "what did Talvrin know on <date>" with no specific subject
    named — a point-in-time inventory of what Talvrin's fact store held,
    grouped by subject_type/metric_id, since there's no single subject to
    reconstruct a full value for in the first place. Matches the
    acceptance test's own literal phrasing: "What did Talvrin know on 15
    September 2026?" names no subject at all.
    """
    knowledge_cutoff = dt.datetime.combine(as_of_date, dt.time.max, tzinfo=dt.UTC)
    facts = (
        (
            await session.execute(
                select(AcceptedFact).where(
                    AcceptedFact.knowledge_range.contains(knowledge_cutoff)
                )
            )
        )
        .scalars()
        .all()
    )

    if not facts:
        return _default_reply(f"what Talvrin knew on {as_of_date.isoformat()}")

    groups: dict[tuple[str, str], list[AcceptedFact]] = {}
    for fact in facts:
        groups.setdefault((fact.subject_type, fact.metric_id), []).append(fact)

    rows = [
        (f"{subject_type} / {metric_id}", f"{len(group)} subject(s) known")
        for (subject_type, metric_id), group in sorted(groups.items())
    ]

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION",
        knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    for group in groups.values():
        # One representative fact per group is enough to make the
        # inventory row auditable - a single curve group alone can hold
        # 14+ individual tenor facts, not all of which need their own
        # evidence-member row just to prove the group itself is real.
        session.add(
            EvidenceMember(
                evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=group[0].id
            )
        )

    return ResearchAnswer(
        text=(
            f"As of the end of {as_of_date.isoformat()}, Talvrin's accepted-fact store held "
            "the following, reconstructed from each fact's own knowledge_range (when it was "
            "ingested, independent of any later correction):"
        ),
        facts=FactTable(title=f"What Talvrin knew on {as_of_date.isoformat()}", rows=rows),
        citations=[
            Citation(
                label="Talvrin accepted-fact store — historical knowledge-time reconstruction",
                meta=f"As known by the end of {as_of_date.isoformat()}",
                pill="SOURCE",
                kind="link",
            )
        ],
        note=(
            "This lists what had been accepted into Talvrin's fact store by this date — ask "
            'about a specific subject (e.g. "what was the UK yield curve on this date") for '
            "its full reconstructed value."
        ),
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


async def _historical_reply(
    session: AsyncSession, query_text: str, as_of_date: dt.date
) -> ResearchAnswer:
    """Routes a recognised historical question to the specific subject it
    names (reusing the same keyword detectors the "live" branches use), or
    to a general point-in-time inventory when no specific subject is named.
    """
    if _mentions_treasury(query_text):
        return await _historical_treasury_curve_reply(session, as_of_date)
    if _mentions_yield_curve(query_text) or _mentions_gilt(query_text):
        return await _historical_yield_curve_reply(session, as_of_date)
    return await _historical_inventory_reply(session, as_of_date)


async def _change_detection_curve_reply(
    session: AsyncSession,
    *,
    metric_id: str,
    benchmark_tenors: list[tuple[Any, str]],
    subject_id_fn: Callable[[Any], uuid.UUID],
    rights_profile_code: str,
    curve_label: str,
    citation_label: str,
    citation_url: str,
) -> ResearchAnswer:
    """Scans every benchmark tenor for a real before/after pair (a
    correction, or the latest two real-world periods — see
    change_detection.detect_change's own docstring for which), then
    classifies each one's materiality with a fixed, deterministic
    threshold (materiality.py) — no AI model call anywhere in this
    function, matching the roadmap's own "works independently of the
    LLM" requirement.
    """
    if not await _display_allowed(session, rights_profile_code):
        return _default_reply(f"what changed in the {curve_label}")

    changed: list[tuple[str, DetectedChange]] = []
    for tenor_key, label in benchmark_tenors:
        result = await detect_change(
            session, subject_id=subject_id_fn(tenor_key), metric_id=metric_id
        )
        if isinstance(result, DetectedChange) and result.old_value != result.new_value:
            changed.append((label, result))

    if not changed:
        return ResearchAnswer(
            text=(
                f"No recorded change in the {curve_label} — every tenor's latest recorded "
                "value matches the one before it."
            ),
            facts=None, citations=[], note=None,
            allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE, evidence_bundle_id=None,
        )

    material = [(label, c) for label, c in changed if c.is_material]

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    rows: list[tuple[str, str]] = []
    lines: list[str] = []
    for label, change in changed:
        session.add(
            EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=change.old_fact_id)
        )
        session.add(
            EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=change.new_fact_id)
        )
        rows.append((label, f"{'MATERIAL' if change.is_material else 'noise'}: {change.explanation}"))
        lines.append(f"• {label}: {change.explanation}")

    summary = (
        f"{len(material)} of {len(changed)} changed tenor(s) crossed the materiality threshold."
        if material
        else f"{len(changed)} tenor(s) changed, but none crossed the materiality threshold — "
        "likely normal day-to-day noise."
    )

    return ResearchAnswer(
        text=f"What changed in the {curve_label}:\n\n" + "\n".join(lines) + f"\n\n{summary}",
        facts=FactTable(title=f"{curve_label} — before vs after", rows=rows),
        citations=[
            Citation(
                label=citation_label, meta=None, pill="SOURCE", kind="doc", url=citation_url
            )
        ],
        note=(
            "Materiality is classified by a fixed, deterministic threshold per metric — "
            "no AI model is involved in this comparison."
        ),
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


async def _change_detection_single_reply(
    session: AsyncSession,
    *,
    subject_id: uuid.UUID,
    metric_id: str,
    rights_profile_code: str,
    subject_label: str,
    display_field: str,
    citation_label: str,
    citation_url: str | None,
) -> ResearchAnswer:
    """The single-subject equivalent of _change_detection_curve_reply - one
    subject_id, not a scan over many tenors.
    """
    if not await _display_allowed(session, rights_profile_code):
        return _default_reply(f"what changed for {subject_label}")

    result = await detect_change(session, subject_id=subject_id, metric_id=metric_id)
    if isinstance(result, NoChangeDetected):
        return ResearchAnswer(
            text=f"No recorded change for {subject_label}: {result.reason}.",
            facts=None, citations=[], note=None,
            allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE, evidence_bundle_id=None,
        )
    if result.old_value == result.new_value:
        return ResearchAnswer(
            text=(
                f"No recorded change for {subject_label} — the latest recorded value "
                "matches the one before it."
            ),
            facts=None, citations=[], note=None,
            allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE, evidence_bundle_id=None,
        )

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    session.add(
        EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=result.old_fact_id)
    )
    session.add(
        EvidenceMember(evidence_bundle_id=bundle.id, kind="FACT", accepted_fact_id=result.new_fact_id)
    )

    rows = [
        ("Before", str(result.old_value.get(display_field))),
        ("After", str(result.new_value.get(display_field))),
        ("Material?", "Yes" if result.is_material else "No"),
    ]

    return ResearchAnswer(
        text=f"What changed for {subject_label}:\n\n{result.explanation}",
        facts=FactTable(title=f"{subject_label} — before vs after", rows=rows),
        citations=[
            Citation(
                label=citation_label, meta=None, pill="SOURCE", kind="doc", url=citation_url
            )
        ],
        note=(
            "Materiality is classified by a fixed, deterministic threshold — no AI model "
            "is involved in this comparison."
        ),
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


async def _change_detection_reply(session: AsyncSession, query_text: str) -> ResearchAnswer:
    """Routes a recognised "what changed" question to the specific subject
    it names, reusing the same keyword detectors the "live" and historical
    branches already use. Scope decision: covers the market-wide subjects
    (both yield curves, FX, macro) — a specific gilt/equity instrument's
    own before/after is a natural, well-scoped follow-up (it would reuse
    this same detect_change core), not yet wired into this dispatcher.
    """
    if _mentions_treasury(query_text):
        return await _change_detection_curve_reply(
            session,
            metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
            benchmark_tenors=_TREASURY_BENCHMARK_TENORS,
            subject_id_fn=treasury_curve_point_subject_id,
            rights_profile_code="treasury.yield-curve",
            curve_label="US Treasury par yield curve",
            citation_label="U.S. Department of the Treasury — Daily Par Yield Curve Rates",
            citation_url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/",
        )
    if _mentions_yield_curve(query_text) or _mentions_gilt(query_text):
        return await _change_detection_curve_reply(
            session,
            metric_id=METRIC_UK_GILT_NOMINAL_SPOT_CURVE,
            benchmark_tenors=_BENCHMARK_TENORS,
            subject_id_fn=curve_point_subject_id,
            rights_profile_code="boe.yield-curve",
            curve_label="UK nominal gilt spot curve",
            citation_label="Bank of England — daily nominal gilt spot curve",
            citation_url="https://www.bankofengland.co.uk/statistics/yield-curves",
        )
    if _mentions_fx(query_text):
        return await _change_detection_single_reply(
            session,
            subject_id=fx_pair_subject_id("GBP", "USD"),
            metric_id=METRIC_FX_SPOT_RATE,
            rights_profile_code="frankfurter.fx",
            subject_label="GBP/USD exchange rate",
            display_field="rate",
            citation_label="Frankfurter — ECB-blended exchange rates",
            citation_url="https://www.frankfurter.app/",
        )
    if (macro_match := _mentioned_macro_series(query_text)) is not None:
        metric_id, country = macro_match
        series_code = _MACRO_SERIES_CODES[(metric_id, country)]
        return await _change_detection_single_reply(
            session,
            subject_id=macro_series_subject_id("WB", "WDI", series_code),
            metric_id=metric_id,
            rights_profile_code="dbnomics.macro",
            subject_label=f"{_MACRO_COUNTRY_LABELS[country]} {_MACRO_INDICATOR_LABELS[metric_id]}",
            display_field="value",
            citation_label="World Bank — World Development Indicators (via DBnomics)",
            citation_url="https://db.nomics.world/",
        )
    return _default_reply(query_text)


async def _approved_spec_id(session: AsyncSession, code: str) -> uuid.UUID | None:
    spec = (
        await session.execute(
            select(CalculationSpecification).where(
                CalculationSpecification.code == code,
                CalculationSpecification.status == "APPROVED",
            )
        )
    ).scalar_one_or_none()
    return spec.id if spec is not None else None


async def _gilt_treasury_spread_reply(session: AsyncSession, query_text: str) -> ResearchAnswer:
    """Computed synchronously, inline — unlike the job-queued calc specs
    (model-implied price, risk metrics), a spread is a single subtraction
    of two already-published, already-reconciled numbers, cheap enough
    that there's no real latency reason to defer it to a background job.
    """
    tenor_years = _mentioned_spread_tenor(query_text)
    spec_id = await _approved_spec_id(session, "gilt_treasury_spread_v1")
    if spec_id is None:
        return _default_reply(f"UK gilt vs US Treasury {tenor_years}Y spread")

    result = await compute_and_persist_gilt_treasury_spread(
        session, tenor_years=tenor_years, calculation_specification_id=spec_id
    )
    if not isinstance(result, SpreadComputed):
        return ResearchAnswer(
            text=(
                f"I can't compute the {tenor_years}-year UK gilt vs US Treasury spread "
                f"yet: {result.reason}."
            ),
            facts=None, citations=[], note=None,
            allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE, evidence_bundle_id=None,
        )

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    session.add(
        EvidenceMember(
            evidence_bundle_id=bundle.id, kind="CALCULATION",
            calculation_result_id=result.calculation_result_id,
        )
    )

    same_date = result.uk_as_of == result.us_as_of
    dates_text = (
        f"both as of {result.uk_as_of.isoformat()}"
        if same_date
        else f"UK as of {result.uk_as_of.isoformat()}, US as of {result.us_as_of.isoformat()}"
    )
    direction = "wider" if result.spread_bp >= 0 else "tighter"
    return ResearchAnswer(
        text=(
            f"The {tenor_years}-year UK gilt yield is currently {abs(result.spread_bp):.2f}bp "
            f"{direction} than the matching US Treasury yield ({dates_text})."
        ),
        facts=FactTable(
            title=f"{tenor_years}-year UK gilt vs US Treasury spread",
            rows=[
                ("Spread (percentage points)", f"{result.spread_pct:+.4f}"),
                ("Spread (basis points)", f"{result.spread_bp:+.2f}"),
                ("UK gilt curve as of", result.uk_as_of.isoformat()),
                ("US Treasury curve as of", result.us_as_of.isoformat()),
            ],
        ),
        citations=[
            Citation(
                label="Calculated by Talvrin — UK gilt curve minus US Treasury curve",
                meta="Talvrin's own cross-market comparison, not a published series",
                pill="SOURCE",
                kind="book",
            )
        ],
        note=(
            "A straightforward subtraction of two already-published, reconciled "
            "benchmark yields — no AI model is involved in this calculation."
        ),
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


async def _holding_period_return_reply(session: AsyncSession, query_text: str) -> ResearchAnswer:
    isin = _mentioned_isin(query_text)
    if isin is None:
        return ResearchAnswer(
            text=(
                "I can work out a holding-period return, but I need to know which gilt — "
                "include its ISIN (e.g. GB0032452392) along with the two dates."
            ),
            facts=None, citations=[], note=None,
            allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION, evidence_bundle_id=None,
        )

    date_range = _mentioned_date_range(query_text)
    assert date_range is not None  # _mentions_holding_period_return already checked this
    start_date, end_date = date_range

    if not await _display_allowed(session, "uk-dmo.gilts"):
        return _default_reply(f"holding-period return for {isin}")

    resolved = await resolve_instrument_by_isin(session, isin)
    if isinstance(resolved, UnresolvedIdentity):
        return ResearchAnswer(
            text=(
                f"I don't have {isin} in the platform's reference data, so I can't "
                "compute a holding-period return for it."
            ),
            facts=None, citations=[], note=None,
            allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION, evidence_bundle_id=None,
        )

    spec_id = await _approved_spec_id(session, "gilt_holding_period_return_v1")
    if spec_id is None:
        return _default_reply(f"holding-period return for {isin}")

    result = await compute_and_persist_holding_period_return(
        session, instrument_id=resolved.instrument_id, start_date=start_date, end_date=end_date,
        calculation_specification_id=spec_id,
    )
    if not isinstance(result, HoldingPeriodReturnComputed):
        return ResearchAnswer(
            text=(
                f"I can't compute a holding-period return for {isin} between "
                f"{start_date.isoformat()} and {end_date.isoformat()} yet: {result.reason}. "
                "This calculation only uses real market close prices, never a model estimate."
            ),
            facts=None, citations=[], note=None,
            allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE, evidence_bundle_id=None,
        )

    bundle = EvidenceBundle(
        purpose_type="FACTUAL_EXPLANATION", knowledge_time=dt.datetime.now(dt.UTC),
        status="ASSEMBLING",
    )
    session.add(bundle)
    await session.flush()
    session.add(
        EvidenceMember(
            evidence_bundle_id=bundle.id, kind="CALCULATION",
            calculation_result_id=result.calculation_result_id,
        )
    )

    return ResearchAnswer(
        text=(
            f"Holding {isin} from {start_date.isoformat()} to {end_date.isoformat()} "
            f"returned {result.holding_period_return_pct:+.2f}% — "
            f"{result.price_return:+.2f} price return plus {result.income_received:.2f} "
            f"in coupon income ({result.coupon_payments_received} payment"
            f"{'s' if result.coupon_payments_received != 1 else ''} received), "
            "on real Tradeweb market close prices at both dates."
        ),
        facts=FactTable(
            title=f"{isin} holding-period return, {start_date.isoformat()} to {end_date.isoformat()}",
            rows=[
                ("Coupon payments received", str(result.coupon_payments_received)),
                ("Income received", f"{result.income_received:.4f}"),
                ("Price return", f"{result.price_return:+.4f}"),
                ("Total return amount", f"{result.total_return_amount:+.4f}"),
                ("Holding-period return", f"{result.holding_period_return_pct:+.2f}%"),
            ],
        ),
        citations=[
            Citation(
                label="Calculated by Talvrin — standard holding-period-return formula",
                meta="Price return + coupon income, over starting dirty price",
                pill="SOURCE",
                kind="book",
            )
        ],
        note=(
            "Both boundary prices are real Tradeweb market close quotes, never a model "
            "estimate — no AI model is involved in this calculation."
        ),
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


def _default_reply(query: str) -> ResearchAnswer:
    return ResearchAnswer(
        text=(
            f'You asked: "{query}"\n\n'
            "Talvrin only answers from accepted facts and deterministic "
            "calculations, and doesn't yet have reconciled data covering this "
            "question — currently live: UK gilt terms and real market prices, "
            "the BoE yield curve, the US Treasury par yield curve, GBP/USD "
            "exchange rates, US equity prices, and UK/US macroeconomic indicators."
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
        (
            await session.execute(
                select(AcceptedFact).where(
                    AcceptedFact.subject_type == "INSTRUMENT",
                    AcceptedFact.metric_id == METRIC_GILT_REFERENCE_TERMS,
                    AcceptedFact.status == "ACTIVE",
                    AcceptedFact.valid_range.contains(now),
                    AcceptedFact.value["redemption_date"].astext.startswith(f"{year}-"),
                )
            )
        )
        .scalars()
        .all()
    )
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
                facts=None,
                citations=[],
                note=None,
                allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
                evidence_bundle_id=None,
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
            # matching (DATA-002: deterministic identity resolution only) -
            # with both sides passed through _normalise_coupon_text first so
            # the three spellings of one coupon compare equal.
            query_normalised = _normalise_coupon_text(query_text)
            narrowed = []
            for inst, fact in matches:
                isin_for_inst = isin_by_instrument_id[inst.id]
                name_normalised = _normalise_coupon_text(str(fact.value["instrument_name"]))
                if name_normalised in query_normalised or (
                    isin_for_inst is not None and isin_for_inst.lower() in query_normalised
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
                    facts=None,
                    citations=[],
                    note=None,
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

    return await _gilt_reference_reply(
        session, instrument=instrument, reference_fact=reference_fact, now=now
    )


async def _gilt_reference_reply(
    session: AsyncSession,
    *,
    instrument: Instrument,
    reference_fact: AcceptedFact,
    now: dt.datetime,
) -> ResearchAnswer:
    """Render one already-resolved gilt's canonical facts - the shared
    tail of _gilt_facts_reply (keyword/year resolution) and _isin_reply
    (exact ISIN resolution): reference terms always, plus the
    model-implied price, Tradeweb market close and risk metrics whenever
    their own rights profile allows. Identity resolution never happens
    here (DATA-002: it happens once, deterministically, in the caller).
    """
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
            url="https://www.dmo.gov.uk/data/pdfdatareport?reportCode=D1A",
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
                    url="https://www.bankofengland.co.uk/statistics/yield-curves",
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

    if await _display_allowed(session, "talvrin.gilt-risk-metrics"):
        risk_metrics_result = await latest_calculation_result(
            session, subject_id=instrument.id, metric_id=METRIC_GILT_RISK_METRICS
        )
        if risk_metrics_result is not None:
            outputs = risk_metrics_result.value["outputs"]
            # Table 13's suppressed statuses (UNAVAILABLE_FINAL_SETTLEMENT,
            # CALCULATION_UNAVAILABLE) carry zeroed, not real, output
            # values - never display those as if they were genuine numbers.
            if outputs["calculation_status"] in ("OK", "EX_DIVIDEND"):
                rows.append(
                    ("Modified duration", f"{Decimal(outputs['modified_duration_full']):.2f} yrs")
                )
                rows.append(("DV01", f"£{Decimal(outputs['dv01_full']):.4f} per £100 nominal"))
                rows.append(("Convexity", f"{Decimal(outputs['convexity_full']):.2f} yr²"))
                if outputs["calculation_status"] == "EX_DIVIDEND":
                    rows.append(("Settlement status", "Ex-dividend"))
                citations.append(
                    Citation(
                        label="Calculated by Talvrin — TAL-FI-GILT-001 v1.0",
                        meta=(
                            f"As of {risk_metrics_result.as_of_date.isoformat()} — "
                            "derived analytic, not a published market figure"
                        ),
                        pill="SOURCE",
                        kind="book",
                    )
                )
                session.add(
                    EvidenceMember(
                        evidence_bundle_id=bundle.id,
                        kind="CALCULATION",
                        calculation_result_id=risk_metrics_result.id,
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


async def _isin_reply(
    session: AsyncSession, *, query_text: str, isin: str
) -> ResearchAnswer:
    """F2 (found live 2026-10-15): a bare ISIN mentioned no keyword any
    intent branch recognised, so "Tell me about GB0032452392" fell through
    to the document-search catch-all and "what is the price of
    GB00BNNGP668?" was answered from an unrelated corpus excerpt. An ISIN
    is already the exact identifier the platform resolves instruments by
    everywhere else (DATA-002), so it gets its own routing: exact alias
    lookup, then that gilt's facts. An unregistered ISIN gets an honest
    "not in our reference data" - never a fuzzy guess at which instrument
    was probably meant, and never the seed gilt's facts (the pre-F2
    behaviour for anything that did reach the gilt branch was to default
    to the seed gilt, which would have been plainly wrong here).
    """
    if not await _display_allowed(session, "uk-dmo.gilts"):
        return _default_reply("gilt reference facts")

    resolved = await resolve_instrument_by_isin(session, isin)
    if isinstance(resolved, UnresolvedIdentity):
        return ResearchAnswer(
            text=(
                f'You asked: "{query_text}"\n\n'
                f"I don't have {isin} in the platform's reference data, so I can't "
                "resolve it to an instrument — Talvrin only answers from exactly "
                "identified, reconciled data, never a guessed match. Reference "
                "coverage today is UK gilts: try a gilt's name, a maturity year, "
                "or ask me about the gilt curve instead."
            ),
            facts=None,
            citations=[],
            note=None,
            allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
            evidence_bundle_id=None,
        )
    assert isinstance(resolved, ResolvedIdentity)
    now = dt.datetime.now(dt.UTC)
    instrument = await session.get(Instrument, resolved.instrument_id)
    reference_fact = (
        await current_accepted_fact_at(
            session,
            subject_id=resolved.instrument_id,
            metric_id=METRIC_GILT_REFERENCE_TERMS,
            at=now,
        )
        if instrument is not None
        else None
    )
    if instrument is None or reference_fact is None:
        # Registered but not a gilt-with-terms (e.g. an equity's ISIN) -
        # still an honest gap, not a fallback to some other instrument.
        return ResearchAnswer(
            text=(
                f'You asked: "{query_text}"\n\n'
                f"{isin} is registered in the reference data but has no gilt "
                "reference terms recorded, so there are no reconciled facts I can "
                "show for it."
            ),
            facts=None,
            citations=[],
            note=None,
            allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
            evidence_bundle_id=None,
        )
    return await _gilt_reference_reply(
        session, instrument=instrument, reference_fact=reference_fact, now=now
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
                url="https://www.bankofengland.co.uk/statistics/yield-curves",
            )
        ],
        note=None,
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


#: A subset of the ~14 published tenors, mirroring _BENCHMARK_TENORS'
#: own narrowing to the figures actually quoted in practice (industry
#: headlines cite "US10Y"/"US30Y", not the 4-month bill) - every published
#: tenor is still ingested as its own curve point, this list only controls
#: which ones render in a reply.
_TREASURY_BENCHMARK_TENORS: list[tuple[str, str]] = [
    ("BC_1MONTH", "1 Month"),
    ("BC_3MONTH", "3 Month"),
    ("BC_6MONTH", "6 Month"),
    ("BC_1YEAR", "1 Year"),
    ("BC_2YEAR", "2 Year"),
    ("BC_5YEAR", "5 Year"),
    ("BC_10YEAR", "10 Year"),
    ("BC_20YEAR", "20 Year"),
    ("BC_30YEAR", "30 Year"),
]


async def _latest_treasury_curve_date(session: AsyncSession) -> dt.datetime | None:
    return (
        await session.execute(
            select(func.lower(AcceptedFact.valid_range))
            .where(
                AcceptedFact.subject_type == SUBJECT_TYPE_TREASURY_CURVE_POINT,
                AcceptedFact.metric_id == METRIC_US_TREASURY_PAR_YIELD_CURVE,
                AcceptedFact.status == "ACTIVE",
            )
            .order_by(func.lower(AcceptedFact.valid_range).desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _treasury_curve_point_facts_at(
    session: AsyncSession, *, at: dt.datetime
) -> list[AcceptedFact]:
    return list(
        (
            await session.execute(
                select(AcceptedFact).where(
                    AcceptedFact.subject_type == SUBJECT_TYPE_TREASURY_CURVE_POINT,
                    AcceptedFact.metric_id == METRIC_US_TREASURY_PAR_YIELD_CURVE,
                    AcceptedFact.status == "ACTIVE",
                    AcceptedFact.valid_range.contains(at),
                )
            )
        )
        .scalars()
        .all()
    )


async def _treasury_yield_curve_reply(session: AsyncSession) -> ResearchAnswer:
    """Mirrors _yield_curve_reply's own shape exactly: the published par
    yield curve itself, not a single headline number, since the feed
    directly names every tenor's own constant-maturity yield (see
    treasury_yield_curve/mapping.py's docstring for why tenor identity is
    the source's own field name, never a derived fractional-year number).
    """
    if not await _display_allowed(session, "treasury.yield-curve"):
        return _default_reply("US Treasury yield curve")

    latest_date = await _latest_treasury_curve_date(session)
    if latest_date is None:
        return _default_reply("US Treasury yield curve")

    curve_facts = await _treasury_curve_point_facts_at(session, at=latest_date)
    if not curve_facts:
        return _default_reply("US Treasury yield curve")

    by_field = {f.value["tenor_field"]: f for f in curve_facts}
    rows: list[tuple[str, str]] = []
    used_facts: list[AcceptedFact] = []
    for field, label in _TREASURY_BENCHMARK_TENORS:
        fact = by_field.get(field)
        if fact is None:
            continue
        rows.append((label, f"{fact.value['par_yield_pct']}%"))
        used_facts.append(fact)

    if not rows:
        return _default_reply("US Treasury yield curve")

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
    # newest - a curve pill must never claim to be fresher than its
    # least-fresh contributing point.
    oldest_knowledge_time = min(
        fact.knowledge_range.lower for fact in used_facts if fact.knowledge_range.lower is not None
    )
    return ResearchAnswer(
        text=(
            f"Here is the US Treasury's daily par yield curve as of {as_of} "
            "— the government's own published constant-maturity yields, not "
            "any specific security's traded price."
        ),
        facts=FactTable(title="US Treasury par yield curve", rows=rows),
        citations=[
            Citation(
                label="U.S. Department of the Treasury — Daily Par Yield Curve Rates",
                meta=f"Published {as_of}",
                pill=compute_freshness(
                    metric_id=METRIC_US_TREASURY_PAR_YIELD_CURVE,
                    knowledge_time=oldest_knowledge_time,
                ),
                kind="doc",
                url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/",
            )
        ],
        note=None,
        allowed_output_type=AllowedOutputType.FACTUAL_EVIDENCE,
        evidence_bundle_id=bundle.id,
    )


def _not_yet_connected_reply(query_text: str, *, asset_class: str) -> ResearchAnswer:
    """Honest stand-in for a whole family of functions removed 2026-10-21:
    each used to return hand-typed, fabricated prices/ratios/yields dressed
    up with fake citations to SEC EDGAR/Federal Reserve/AMFI/TradingView and
    a false "Bitemporal Fact State: CANONICAL (reconciled)" claim - none of
    it ever touched accepted_fact or a real connector. A live production
    query ("what is CPI" for India) was answered with a fabricated Apple
    equity-research report because one of these (_equity_deep_research_reply)
    had an unconditional else-branch defaulting to Apple for any unmatched
    query, reachable via `query_text.strip().startswith("[")` alone. This
    platform's entire premise is that it never answers without a real,
    traceable source (see policy.pdp, AI-001) - a fabricated answer is a
    worse failure mode than an honest "not yet connected" for an asset
    class this platform genuinely doesn't have a live source for yet.
    """
    return ResearchAnswer(
        text=(
            f'You asked about {asset_class}.\n\n'
            "Talvrin doesn't have a real, reconciled data source connected for "
            f"{asset_class} yet, so it won't answer with invented figures - it only "
            "ever answers from accepted facts and deterministic calculations that "
            "trace back to a verifiable source. Currently live: UK gilt terms and "
            "prices, the BoE yield curve, the US Treasury par yield curve, GBP/USD "
            "exchange rates, US equity prices for a small pilot list, and UK/US "
            "macroeconomic indicators."
        ),
        facts=None,
        citations=[],
        note=None,
        allowed_output_type=AllowedOutputType.NEUTRAL_EDUCATION,
        evidence_bundle_id=None,
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
        (
            await session.execute(
                select(FactObservationLink.source_observation_id).where(
                    FactObservationLink.accepted_fact_id == accepted_fact_id
                )
            )
        )
        .scalars()
        .all()
    )
    if not observation_ids:
        return 0
    rights_profile_ids = (
        (
            await session.execute(
                select(SourceObservation.rights_profile_id).where(
                    SourceObservation.id.in_(observation_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    return len(set(rights_profile_ids))


async def _fact_provenance(
    session: AsyncSession, accepted_fact_id: uuid.UUID
) -> tuple[set[uuid.UUID], set[str]]:
    """Distinct rights_profile_ids AND publisher names backing one accepted
    fact, via the same FactObservationLink join _confirming_source_count
    already uses — extended one hop further (SourceArtifact -> Dataset ->
    Source) to resolve the actual publisher's name, not just count profiles.
    Empty sets for a fact with no linked observations at all (shouldn't
    happen for a real ingested fact, but never crashes over it).
    """
    rows = (
        await session.execute(
            select(SourceObservation.rights_profile_id, Source.name)
            .select_from(FactObservationLink)
            .join(
                SourceObservation,
                FactObservationLink.source_observation_id == SourceObservation.id,
            )
            .join(SourceArtifact, SourceObservation.source_artifact_id == SourceArtifact.id)
            .join(Dataset, SourceArtifact.dataset_id == Dataset.id)
            .join(Source, Dataset.source_id == Source.id)
            .where(FactObservationLink.accepted_fact_id == accepted_fact_id)
        )
    ).all()
    return {row[0] for row in rows}, {row[1] for row in rows}


#: Only the actions a user would actually recognise as describing further
#: use of a fact, not Talvrin's own internal plumbing (retrieve/store/cache
#: aren't meaningful to show, and display is trivial - anything reaching
#: this function is already being displayed, or the PDP would have blocked
#: it before evidence assembly ever started).
_SURFACED_RIGHTS_ACTIONS: tuple[RightsAction, ...] = ("export", "redistribute", "ai")
_RIGHTS_ACTION_LABELS: dict[str, str] = {
    "export": "Export",
    "redistribute": "Redistribution",
    "ai": "AI-composed use",
}


async def _permitted_use_summary(
    session: AsyncSession, rights_profile_ids: set[uuid.UUID]
) -> str | None:
    """A short, plain-language summary of what a user may do with a fact
    beyond viewing it - never the raw PDP decision trace, a rights-profile
    code, or any other internal policy detail (RIGHTS-001's own per-action
    doctrine means "permitted to display" says nothing about export or
    redistribution, so those are surfaced explicitly instead of implied).

    None when no governing rights profile can be resolved at all - an
    honest "unknown", never a fabricated default.

    Conservative across more than one governing source (a fact backed by
    several agreeing observations): ALL of them must allow a given action
    for the combined fact to be described as permitted for it - the most
    restrictive source's limitation applies to the whole fact, matching
    evaluate_action's own fail-closed doctrine.
    """
    if not rights_profile_ids:
        return None

    parts: list[str] = []
    for action in _SURFACED_RIGHTS_ACTIONS:
        decisions = [
            await evaluate_action(session, action, profile_id)
            for profile_id in rights_profile_ids
        ]
        allowed = all(decision == RightsDecision.ALLOW for decision in decisions)
        label = _RIGHTS_ACTION_LABELS[action]
        parts.append(f"{label}: {'permitted' if allowed else 'not permitted'}")
    return " · ".join(parts)


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
                url="https://www.bankofengland.co.uk/boeapps/database/",
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
    if len(matches) > 1:
        # A real, previously-undiscovered collision: a dual-listed issuer
        # (e.g. Vodafone on both LSE and, via ADR, NASDAQ) is onboarded as
        # two separate instruments sharing the same bare ticker symbol
        # ("VOD"), so a bare-symbol query matches both and was silently
        # treated as ambiguous - even when only one listing is actually
        # tracked (PILOT_EQUITIES only ingests the NASDAQ/NYSE line, never
        # the LSE one). This is not fuzzy resolution: the symbol match
        # itself is still exact on both candidates; this only breaks the
        # tie by which one has real accepted_fact data, which is a fact
        # about data availability, not a guess about identity.
        with_data = [
            m
            for m in matches
            if await latest_accepted_fact(
                session, subject_id=m[0].id, metric_id=METRIC_EQUITY_EOD_PRICE
            )
            is not None
        ]
        if len(with_data) == 1:
            return with_data[0]
    return None


async def _equity_price_reply(session: AsyncSession, query_text: str) -> ResearchAnswer | None:
    """Returns None (never a reply) when the query doesn't deterministically
    match exactly one onboarded equity - the caller falls through to the
    next intent branch rather than treating "no company mentioned" as a
    data gap worth a NEUTRAL_EDUCATION reply of its own.
    """
    if session is None:
        return None
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
                url="https://twelvedata.com/",
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
        text=(f"{country_label} {indicator_label}, {fact.value['period']}: {formatted_value}."),
        facts=FactTable(title=f"{country_label} — {indicator_label}", rows=rows),
        citations=[
            Citation(
                label="World Bank — World Development Indicators (via DBnomics)",
                meta=f"As of {knowledge_time.isoformat()}",
                pill=compute_freshness(metric_id=metric_id, knowledge_time=knowledge_time, now=now),
                kind="link",
                url="https://db.nomics.world/",
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


#: The frontend prepends this wrapper to the wire query whenever the user has
#: an asset "tagged" in the compose box (App.tsx's `wireQuery`), on every
#: message sent while that tag is active - including ones with nothing to do
#: with the tagged asset. No backend code has ever intentionally parsed this
#: format (confirmed: nothing in this codebase references "Tagged Asset"), so
#: it was reaching the keyword classifiers below as untouched text - a tagged
#: Apple caused a live "what is CPI" question to be classified as an equity
#: query because the wrapper itself contains "Apple"/"AAPL". Stripped here so
#: classification and every downstream branch sees only the real question.
_TAGGED_ASSET_CONTEXT_PREFIX = re.compile(r"^\[Context: Tagged Asset [^\]]*\]\.\s*Query:\s*", re.I)

logger = logging.getLogger(__name__)


async def _dispatch_answer(
    session: AsyncSession, query_text: str, http: httpx.AsyncClient | None
) -> ResearchAnswer:
    """The big intent-classification chain, pulled out of
    assemble_research_answer so that function can wrap this call in a
    safety net - this part alone is where every keyword/regex branch and
    every per-branch DB query lives, i.e. the real surface area for an
    unanticipated bug in any one of them.
    """
    if _is_advice(query_text):
        answer = _advice_reply()
    elif _is_greeting(query_text):
        answer = _greeting_reply()
    elif _is_closing(query_text):
        answer = _closing_reply()
    elif _is_help_request(query_text):
        answer = _help_reply()
    elif (historical_cutoff := _mentioned_historical_cutoff(query_text)) is not None:
        # Checked before every other keyword branch: a historical question
        # ("what did Talvrin know on 15 September 2026?") can still mention
        # "gilt"/"treasury"/"yield curve", and those branches only ever
        # reconstruct TODAY's current state - routing here first is what
        # lets _historical_reply re-apply the same subject keywords against
        # a genuine point-in-time reconstruction instead.
        answer = await _historical_reply(session, query_text, historical_cutoff)
    elif _mentions_change_query(query_text):
        # Checked before every other keyword branch, same reasoning as the
        # historical branch above: "what's changed in the gilt yield
        # curve?" still mentions "gilt"/"yield curve", and those branches
        # only ever show today's single current state, never a before/
        # after comparison.
        answer = await _change_detection_reply(session, query_text)
    elif _mentions_holding_period_return(query_text):
        # Checked before _mentions_isin/_mentions_gilt: a return question
        # ("what was my return on GB0032452392 from ... to ...?") still
        # names an ISIN and the word "gilt", and those branches only ever
        # show current reference facts, never a two-date return.
        answer = await _holding_period_return_reply(session, query_text)
    elif _SPREAD_TRIGGER_PATTERN.search(query_text) and (
        _mentions_treasury(query_text) or _mentions_gilt(query_text)
    ):
        answer = await _gilt_treasury_spread_reply(session, query_text)
    elif _mentions_accrued(query_text):
        answer = await _document_backed_accrued_reply(session) or _accrued_reply()
    elif _mentions_treasury(query_text):
        # Checked before _mentions_yield_curve: that pattern's generic
        # "<N> year ... yield" fallback (added for a UK gilt-tenor miss)
        # also matches "US 10 year treasury yield" - found live, 2026-10-22,
        # misrouting a genuine Treasury question to the UK curve reply.
        # Safe to check first because _mentions_treasury already excludes
        # anything gilt-related (its own "gilt"/"glit"/_mentions_gilt
        # guard), so nothing intended for the UK branch is stolen here.
        answer = await _treasury_yield_curve_reply(session)
    elif _mentions_yield_curve(query_text):
        answer = await _yield_curve_reply(session)
    elif _mentions_fx(query_text):
        answer = await _fx_rate_reply(session)
    elif (macro_match := _mentioned_macro_series(query_text)) is not None:
        answer = await _macro_reply(session, *macro_match)
    elif (equity_answer := await _equity_price_reply(session, query_text)) is not None:
        answer = equity_answer
    elif (isin := _mentioned_isin(query_text)) is not None:
        # F2: checked before the keyword branches so an ISIN resolves to
        # the instrument it names, whether or not the query also says
        # "gilt" - never the seed gilt (the gilt branch's no-year
        # default) and never the document catch-all.
        answer = await _isin_reply(session, query_text=query_text, isin=isin)
    elif _mentions_market_structure(query_text):
        # Checked before _mentions_gilt - see _MARKET_STRUCTURE_PATTERN's
        # own comment for the real "Gilt-Edged Market Maker" misroute
        # this guards against.
        answer = await _document_backed_market_structure_reply(
            session, query_text, http
        ) or _default_reply(query_text)
    elif _mentions_gilt(query_text):
        if _prefers_document_explanation(query_text):
            # F12: an explanation-framed question that merely mentions
            # "gilt" - the instrument-facts branch can only ever render
            # one gilt's data table, which is never an answer to
            # "how"/"why". Document corpus first; fall back to the gilt
            # facts when nothing there matches, so this is never worse
            # than the pre-F12 routing.
            answer = (
                await _document_backed_fallback_reply(session, query_text, http)
                or await _gilt_facts_reply(session, query_text)
            )
        else:
            answer = await _gilt_facts_reply(session, query_text)
    elif _mentions_etf(query_text):
        answer = _not_yet_connected_reply(query_text, asset_class="ETFs")
    elif _mentions_crypto(query_text):
        answer = _not_yet_connected_reply(query_text, asset_class="cryptocurrencies")
    elif _mentions_commodity(query_text):
        answer = _not_yet_connected_reply(query_text, asset_class="commodities")
    elif _mentions_ipo(query_text):
        answer = _not_yet_connected_reply(query_text, asset_class="IPOs")
    elif _mentions_mutual_fund(query_text):
        answer = _not_yet_connected_reply(query_text, asset_class="mutual funds")
    elif _mentions_global_index(query_text):
        answer = _not_yet_connected_reply(query_text, asset_class="global market indices")
    elif _mentions_deep_equity(query_text):
        answer = _not_yet_connected_reply(
            query_text, asset_class="equity fundamentals / deep research"
        )
    else:
        answer = await _document_backed_fallback_reply(session, query_text, http) or _default_reply(
            query_text
        )
    return answer


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
    query_text = _TAGGED_ASSET_CONTEXT_PREFIX.sub("", query_text, count=1)
    try:
        answer = await _dispatch_answer(session, query_text, http)
    except Exception:
        # Defense in depth: an unanticipated bug in any single branch of
        # _dispatch_answer's classification chain must still produce the
        # platform's normal, honest "ask within these limits" reply, never
        # a raw internal error - found live, 2026-10-28: two real chat
        # queries surfaced "An internal error occurred" instead of this.
        # The real exception is still logged here, not silently discarded.
        logger.exception(
            "assemble_research_answer: dispatch failed for query %r", query_text
        )
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
    # Knowledge/ingestion time ONLY - when Talvrin came to hold this exact
    # value, never the real-world date/period it describes (see
    # effective_time for that). Previously conflated for CALCULATION items
    # (as_of held the market-effective as_of_date, not a knowledge time at
    # all) - PRD P2's own traceability gap, fixed here: as_of is now always
    # "when Talvrin knew this", uniformly across every kind.
    as_of: str | None
    # Market-effective time - the real-world date/period this value
    # describes. Deliberately a SEPARATE field from as_of: the whole point
    # of showing both is that they can differ (an ingestion lag, or - for a
    # correction - the same effective date known at two different times).
    effective_time: str | None = None
    # Plain publisher/computation attribution (e.g. "Bank of England", or
    # "Talvrin calculation (gilt_price_yield_v1 v1)") - never a raw
    # rights-profile code or policy-engine identifier.
    source: str | None = None
    # A short, plain-language summary of what a user may do with this fact
    # beyond viewing it (export/redistribute/AI-composed use) - RIGHTS-001's
    # own per-action doctrine means "permitted to display" says nothing
    # about these, so they're surfaced explicitly rather than implied.
    # None when no governing rights profile can be resolved at all, never
    # a fabricated default (see _permitted_use_summary).
    permitted_use: str | None = None
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


async def _resolve_bundle_items(session: AsyncSession, bundle_id: uuid.UUID) -> list[EvidenceItem]:
    """FACT/CALCULATION/DOCUMENT_SPAN rendering shared by every bundle
    reader - keyed on bundle_id, not research_message_id, so a bundle can
    be read before (or without ever) being attached to a persisted
    message.
    """
    members = (
        (
            await session.execute(
                select(EvidenceMember).where(EvidenceMember.evidence_bundle_id == bundle_id)
            )
        )
        .scalars()
        .all()
    )

    # Batched (WHERE id IN (...)) rather than one session.get() per member -
    # a bundle backing an AI-composed answer can have many members, and
    # this function is on the /research request path (via
    # get_evidence_bundle_items -> ai_gateway.evidence_path), not just a
    # script. Facts/results are looked up in a dict afterward so the
    # per-member loop below still emits items in the SAME order as
    # `members` - citation indices elsewhere are positional, so this must
    # never reorder.
    fact_ids = {
        m.accepted_fact_id for m in members if m.kind == "FACT" and m.accepted_fact_id is not None
    }
    result_ids = {
        m.calculation_result_id
        for m in members
        if m.kind == "CALCULATION" and m.calculation_result_id is not None
    }

    facts_by_id: dict[uuid.UUID, AcceptedFact] = {}
    if fact_ids:
        fact_rows = (
            (await session.execute(select(AcceptedFact).where(AcceptedFact.id.in_(fact_ids))))
            .scalars()
            .all()
        )
        facts_by_id = {fact.id: fact for fact in fact_rows}

    results_by_id: dict[uuid.UUID, CalculationResult] = {}
    if result_ids:
        result_rows = (
            (
                await session.execute(
                    select(CalculationResult).where(CalculationResult.id.in_(result_ids))
                )
            )
            .scalars()
            .all()
        )
        results_by_id = {result.id: result for result in result_rows}

    items: list[EvidenceItem] = []
    for member in members:
        if member.kind == "FACT" and member.accepted_fact_id is not None:
            fact = facts_by_id.get(member.accepted_fact_id)
            if fact is not None:
                assert fact.knowledge_range.lower is not None  # our own rows always set this
                fact_rights_profile_ids, source_names = await _fact_provenance(session, fact.id)
                items.append(
                    EvidenceItem(
                        kind="FACT",
                        subject_type=fact.subject_type,
                        metric_id=fact.metric_id,
                        value=fact.value,
                        basis=None,
                        as_of=fact.knowledge_range.lower.isoformat(),
                        effective_time=(
                            fact.valid_range.lower.isoformat()
                            if fact.valid_range.lower is not None
                            else None
                        ),
                        source=", ".join(sorted(source_names)) if source_names else None,
                        permitted_use=await _permitted_use_summary(
                            session, fact_rights_profile_ids
                        ),
                    )
                )
        elif member.kind == "CALCULATION" and member.calculation_result_id is not None:
            result = results_by_id.get(member.calculation_result_id)
            if result is not None:
                input_fact_ids = (
                    (
                        await session.execute(
                            select(CalculationInput.accepted_fact_id).where(
                                CalculationInput.calculation_result_id == result.id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                calc_rights_profile_ids: set[uuid.UUID] = set()
                for input_fact_id in input_fact_ids:
                    input_rights_ids, _ = await _fact_provenance(session, input_fact_id)
                    calc_rights_profile_ids |= input_rights_ids

                spec = await session.get(
                    CalculationSpecification, result.calculation_specification_id
                )
                spec_label = f"{spec.code} v{spec.version}" if spec is not None else "unknown spec"
                items.append(
                    EvidenceItem(
                        kind="CALCULATION",
                        subject_type=result.subject_type,
                        metric_id=result.metric_id,
                        value=result.value,
                        basis=result.basis,
                        # Knowledge time for a CALCULATION is when Talvrin
                        # computed it, NOT the market-effective date the
                        # calculation is for (that's effective_time, below)
                        # - previously conflated here, part of the gap this
                        # feature exists to close.
                        as_of=result.created_at.isoformat(),
                        effective_time=result.as_of_date.isoformat(),
                        source=f"Talvrin calculation ({spec_label})",
                        permitted_use=await _permitted_use_summary(
                            session, calc_rights_profile_ids
                        ),
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
