"""reference schema — jurisdiction-neutral canonical instrument/issuer
registry (DATA-001). Platform-wide, not account-scoped: no RLS here.

Deliberate P0 simplification: currency/venue codes are plain strings, not
FKs to dedicated currency/venue/calendar reference tables — DATA-001
mentions those as eventual reference entities, but this plan's Week 4 scope
was explicitly the 6 tables below; normalizing currencies/venues/calendars
is deferred rather than guessed at now.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class Issuer(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "issuer"
    __table_args__ = {"schema": "reference"}

    name: Mapped[str] = mapped_column(String(300))
    country_code: Mapped[str | None] = mapped_column(String(2), default=None)  # ISO 3166-1 alpha-2
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class IssuerAlias(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """External identifiers (e.g. LEI) are aliases only, never the primary
    key (DATA-001) — the opaque UUIDv7 `id` on Issuer is the only PK.
    """

    __tablename__ = "issuer_alias"
    __table_args__ = (
        UniqueConstraint("alias_type", "alias_value", name="uq_issuer_alias_type_value"),
        {"schema": "reference"},
    )

    issuer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference.issuer.id"), index=True
    )
    alias_type: Mapped[str] = mapped_column(String(32))  # e.g. LEI, LEGAL_NAME
    alias_value: Mapped[str] = mapped_column(String(200))


class Instrument(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "instrument"
    __table_args__ = {"schema": "reference"}

    issuer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference.issuer.id"), index=True
    )
    # Discriminates which asset-adapter table (e.g. fi_sovereign_terms)
    # holds this instrument's type-specific terms — one row per instrument
    # in exactly one adapter table, matched on instrument_type.
    instrument_type: Mapped[str] = mapped_column(String(32), index=True)  # e.g. FI_SOVEREIGN
    name: Mapped[str] = mapped_column(String(300))
    currency_code: Mapped[str] = mapped_column(String(3))  # ISO 4217
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class InstrumentAlias(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """ISIN/CUSIP/SEDOL/FIGI/ticker — aliases only, never the PK. This is
    exactly what P1's deterministic identity resolution (exact ISIN match,
    never fuzzy) will query against.
    """

    __tablename__ = "instrument_alias"
    __table_args__ = (
        UniqueConstraint("alias_type", "alias_value", name="uq_instrument_alias_type_value"),
        {"schema": "reference"},
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference.instrument.id"), index=True
    )
    alias_type: Mapped[str] = mapped_column(String(32))  # ISIN, CUSIP, SEDOL, FIGI, TICKER
    alias_value: Mapped[str] = mapped_column(String(64))


class InstrumentListing(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Where/how an instrument trades. Minimal shape — no venue master
    table yet (see module docstring)."""

    __tablename__ = "instrument_listing"
    __table_args__ = {"schema": "reference"}

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference.instrument.id"), index=True
    )
    venue_code: Mapped[str] = mapped_column(String(32))  # e.g. LSE, OTC
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class FiSovereignTerms(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The gilt/Treasury asset-adapter table (instrument_type=FI_SOVEREIGN)
    — fields chosen to exactly back the frontend's existing gilt fact table
    (frontend/src/data/mockReply.ts GILT_REPLY): instrument, ISIN (via
    instrument_alias), coupon, maturity, day count, ex-dividend, currency
    (via instrument.currency_code).
    """

    __tablename__ = "fi_sovereign_terms"
    __table_args__ = {"schema": "reference"}

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference.instrument.id"), unique=True
    )
    coupon_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6))  # percent, e.g. 4.250000
    coupon_frequency: Mapped[str] = mapped_column(String(16))  # e.g. SEMI_ANNUAL
    day_count_convention: Mapped[str] = mapped_column(String(32))  # e.g. ACT_ACT_ICMA
    first_issue_date: Mapped[dt.date] = mapped_column(Date())
    maturity_date: Mapped[dt.date] = mapped_column(Date())
    ex_dividend_days: Mapped[int]


class FiSovereignDiscountTerms(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The US Treasury Bill asset-adapter table
    (instrument_type=FI_SOVEREIGN_DISCOUNT) — a genuinely different shape
    from FiSovereignTerms, not a reused one with blank coupon fields: Bills
    (and Cash Management Bills, discriminated by `is_cash_management_bill`,
    not a separate instrument_type - TreasuryDirect itself reports CMBs as
    securityType="Bill" with a boolean flag, confirmed live 2026-10-26) are
    discount instruments with no periodic coupon at all. `high_rate` is the
    auction's own discount rate; `investment_rate` is the coupon-equivalent
    (bond-equivalent) yield TreasuryDirect publishes alongside it - both are
    auction-day snapshots, the same "rate fixed at the instrument's own
    auction" limitation FiSovereignTerms.coupon_rate already carries for
    Notes/Bonds, not a new one introduced here.
    """

    __tablename__ = "fi_sovereign_discount_terms"
    __table_args__ = {"schema": "reference"}

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference.instrument.id"), unique=True
    )
    high_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6))  # percent, discount rate
    investment_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6))  # percent, coupon-equivalent
    is_cash_management_bill: Mapped[bool] = mapped_column(Boolean, default=False)
    # ACT/360 is the standard, market-wide T-bill discount convention - not
    # TreasuryDirect-feed-derived, the same "named, not guessed" treatment
    # onboard_all_treasury_securities.py already gives ACT_ACT_TREASURY.
    day_count_convention: Mapped[str] = mapped_column(String(32))
    first_issue_date: Mapped[dt.date] = mapped_column(Date())
    maturity_date: Mapped[dt.date] = mapped_column(Date())


class FiSovereignFrnTerms(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The US Treasury Floating Rate Note asset-adapter table
    (instrument_type=FI_SOVEREIGN_FRN). TreasuryDirect reports an FRN with
    securityType="Note" and floatingRate="Yes" (confirmed live 2026-10-26,
    same flag-not-type-field pattern as TIPS' inflationProtected) - a
    genuinely different shape from FiSovereignTerms since an FRN has no
    fixed coupon_rate at all, only a spread over its reference index (the
    13-week Treasury Bill discount rate - Treasury's only FRN program) plus
    the index rate determined at its own auction.
    """

    __tablename__ = "fi_sovereign_frn_terms"
    __table_args__ = {"schema": "reference"}

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reference.instrument.id"), unique=True
    )
    spread: Mapped[Decimal] = mapped_column(Numeric(9, 6))  # percent, over the index rate
    index_determination_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6))  # percent, at auction
    frequency_of_interest_payments: Mapped[str] = mapped_column(String(16))  # e.g. QUARTERLY
    day_count_convention: Mapped[str] = mapped_column(String(32))
    first_issue_date: Mapped[dt.date] = mapped_column(Date())
    maturity_date: Mapped[dt.date] = mapped_column(Date())
