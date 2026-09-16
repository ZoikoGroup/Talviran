"""Unit tests for evidence/service.py's intent classification — ported
verbatim from frontend/src/data/mockReply.ts's regexes (genuinely correct
product behaviour worth keeping per the plan this was built from), so these
prove the port is faithful, not that the patterns themselves are novel.
"""

from app.modules.evidence.service import (
    _is_advice,
    _mentions_accrued,
    _mentions_gilt,
    _mentions_yield_curve,
)

ADVICE_QUERIES = [
    "should I buy this gilt?",
    "Is it a good investment?",
    "what should i invest in right now",
    "what's the best treasury pick for 2027",
    "what's the price target on this bond",
    "is this worth investing in",
]

NON_ADVICE_QUERIES = [
    "what is accrued interest?",
    "tell me about the 4.25% Treasury Stock 2036",
    "explain clean vs dirty price",
]


def test_advice_patterns_are_detected() -> None:
    for query in ADVICE_QUERIES:
        assert _is_advice(query), query


def test_non_advice_queries_are_not_flagged() -> None:
    for query in NON_ADVICE_QUERIES:
        assert not _is_advice(query), query


def test_gilt_mentions_detected() -> None:
    assert _mentions_gilt("tell me about the 2036 gilt")
    assert _mentions_gilt("Treasury Gilt facts please")
    assert not _mentions_gilt("what's the weather like")


def test_accrued_mentions_detected() -> None:
    assert _mentions_accrued("what is accrued interest")
    assert _mentions_accrued("explain the day count convention")
    assert _mentions_accrued("clean vs dirty price")
    assert _mentions_accrued("ACT/ACT explained")
    assert not _mentions_accrued("what's the weather like")


def test_ex_dividend_mentions_are_treated_as_accrued() -> None:
    # Found missing during live testing: the accrued-interest explanation's
    # own text covers ex-dividend periods, but the query pattern didn't
    # recognize the term itself - a real classification miss, not a "no
    # data" case.
    assert _mentions_accrued("how does the ex-dividend period work")
    assert _mentions_accrued("what is the ex dividend date")
    assert _mentions_accrued("explain ex-dividend")


def test_advice_takes_priority_even_if_it_also_mentions_gilt() -> None:
    query = "should I buy this gilt?"
    assert _is_advice(query)
    assert _mentions_gilt(query)  # both match; caller must check advice first


def test_yield_curve_mentions_detected() -> None:
    assert _mentions_yield_curve("what's the yield curve look like?")
    assert _mentions_yield_curve("show me the spot curve")
    assert _mentions_yield_curve("what are interest rates right now")
    assert _mentions_yield_curve("what does the Bank of England say")
    assert _mentions_yield_curve("what's the BoE curve at 10 years")
    assert not _mentions_yield_curve("tell me about the 2036 gilt")
    assert not _mentions_yield_curve("what's the weather like")


def test_yield_curve_also_mentioning_gilt_is_still_yield_curve() -> None:
    # caller must check yield-curve before the more general gilt-facts branch
    query = "what's the yield curve for gilts?"
    assert _mentions_yield_curve(query)
    assert _mentions_gilt(query)
