"""Production implementation of UK DMO's conventional-gilt price/yield
formulae ("Formulae for Calculating Gilt Prices from Yields", 4th edition,
18 Dec 2024, Section One). Verified against DMO's own worked examples in
`yldconv.pdf` (8 June 1998) — see golden/v1/corpus.json, sourced directly
from that document, not invented.

Scope: CONVENTIONAL gilts, REGULAR (non-first-period) settlements only.
Index-linked gilts, strips, and long/short first dividend periods are
explicitly out of scope for v1 — the DMO document covers them with
different formulae this module does not implement. A settlement inside a
gilt's first dividend period, or against an index-linked/strip instrument,
must be rejected by the caller before reaching this module, not silently
mishandled here.

All internal arithmetic runs at 50 significant digits (`localcontext`) to
avoid the accumulated rounding error a lower default precision would
introduce across nested powers/divisions — this is what let the production
implementation reproduce the DMO's 6-9dp worked examples exactly. Output is
NOT rounded to the penny here (per DMO's own doc, that rounding is a
settlement-time convention, not part of the pricing formula itself); the
caller rounds when producing a trade/settlement value.

`yield_from_price` for n=0 solves algebraically (DMO gives the closed
form); for n>=1 DMO's own paper states no closed form exists, so a
bisection solve against `dirty_price_from_yield` is used instead — bounded,
deterministic, and reproducible (fixed bracket, fixed iteration cap).
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

_PRECISION = 50
_YIELD_SEARCH_LOWER = Decimal("-0.5")  # -50%: comfortably below any real gilt yield
_YIELD_SEARCH_UPPER = Decimal("1.0")  # 100%: comfortably above any real gilt yield
_BISECTION_TOLERANCE = Decimal("1E-12")
_BISECTION_MAX_ITERATIONS = 200


@dataclass(frozen=True)
class ConventionalGiltInputs:
    """Everything DMO's formula needs, already resolved by the caller from
    the instrument's real terms and the settlement date — this module does
    no date arithmetic itself, only the pricing formula.
    """

    coupon_per_100: Decimal  # c
    coupons_per_year: int  # f (2 for every current gilt)
    days_to_next_quasi_coupon: int  # r
    days_in_quasi_coupon_period: int  # s
    full_quasi_coupon_periods_remaining: int  # n
    next_cash_flow: Decimal  # d1 (0 if settling ex-dividend)
    next_but_one_cash_flow: Decimal  # d2


def _discount_factor(yield_decimal: Decimal, f: int) -> Decimal:
    return 1 / (1 + yield_decimal / f)


def dirty_price_from_yield(inputs: ConventionalGiltInputs, yield_decimal: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        f = inputs.coupons_per_year
        r = Decimal(inputs.days_to_next_quasi_coupon)
        s = Decimal(inputs.days_in_quasi_coupon_period)
        n = inputs.full_quasi_coupon_periods_remaining
        c = inputs.coupon_per_100
        d1 = inputs.next_cash_flow
        d2 = inputs.next_but_one_cash_flow

        v = _discount_factor(yield_decimal, f)

        if n == 0:
            return v ** (r / s) * (d1 + 100)

        bracket = (c * v**2) / (f * (1 - v)) * (1 - v ** (n - 1))
        return v ** (r / s) * (d1 + d2 * v + bracket + 100 * v**n)


def _yield_from_price_n_zero(inputs: ConventionalGiltInputs, dirty_price: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        f = inputs.coupons_per_year
        r = Decimal(inputs.days_to_next_quasi_coupon)
        s = Decimal(inputs.days_in_quasi_coupon_period)
        d1 = inputs.next_cash_flow
        return f * (((d1 + 100) / dirty_price) ** (s / r) - 1)


def yield_from_price(inputs: ConventionalGiltInputs, dirty_price: Decimal) -> Decimal:
    """DMO's paper: "it is not possible (in most cases) to solve for yield
    in terms of price algebraically" for n>=1, hence the bisection solve.
    `dirty_price_from_yield` is monotonically decreasing in yield, so
    bisection on a fixed, wide bracket is safe and deterministic.
    """
    if inputs.full_quasi_coupon_periods_remaining == 0:
        return _yield_from_price_n_zero(inputs, dirty_price)

    with localcontext() as ctx:
        ctx.prec = _PRECISION
        low, high = _YIELD_SEARCH_LOWER, _YIELD_SEARCH_UPPER
        price_at_low = dirty_price_from_yield(inputs, low)
        price_at_high = dirty_price_from_yield(inputs, high)
        if not (price_at_high <= dirty_price <= price_at_low):
            raise ValueError(
                f"target price {dirty_price} is outside the solvable bracket "
                f"[{price_at_high}, {price_at_low}] for yields in "
                f"[{_YIELD_SEARCH_LOWER}, {_YIELD_SEARCH_UPPER}]"
            )

        for _ in range(_BISECTION_MAX_ITERATIONS):
            mid = (low + high) / 2
            price_at_mid = dirty_price_from_yield(inputs, mid)
            if abs(price_at_mid - dirty_price) < _BISECTION_TOLERANCE:
                return mid
            # price_at_yield is monotonically decreasing in yield.
            if price_at_mid > dirty_price:
                low = mid
            else:
                high = mid
        return (low + high) / 2


def accrued_interest(
    *, next_cash_flow: Decimal, days_since_previous_quasi_coupon: int,
    days_in_quasi_coupon_period: int, settled_on_or_before_ex_dividend: bool,
) -> Decimal:
    """DMO Section Three, standard dividend periods. `next_cash_flow` is
    d1 as published (i.e. already zero if settlement is ex-dividend) —
    matching d1's own definition, not something this function re-derives.
    """
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        t = Decimal(days_since_previous_quasi_coupon)
        s = Decimal(days_in_quasi_coupon_period)
        if settled_on_or_before_ex_dividend:
            return (t / s) * next_cash_flow
        return (t / s - 1) * next_cash_flow


def clean_price(dirty_price: Decimal, accrued: Decimal) -> Decimal:
    return dirty_price - accrued
