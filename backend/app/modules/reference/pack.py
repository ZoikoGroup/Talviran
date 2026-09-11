"""The pack interface — the seam every future jurisdiction/asset-class
plugs into without forking core code (ENG-ARCH-003's Track T doctrine:
global expansion adds governed packs, never forks the platform).

Deviation from the plan's original wording: this is a plain dataclass, not
a Protocol/ABC. A Protocol implies multiple concrete implementations with
polymorphic behavior to swap between — but a pack isn't behavior, it's
configuration (which jurisdiction, which rights profile, which connectors).
A dataclass says that plainly; a Protocol here would just be ceremony.

connector_codes and calculation_spec_codes are identifiers, not live
objects — app.modules.market.connectors (P1 week 8) and
app.modules.calculation.specs (P1 week 11) don't exist yet. Recording the
identifiers now pins the pack's eventual shape so P1 wires each one to a
real class rather than inventing this list from scratch; resolving them to
importable objects is deliberately deferred, not stubbed with fake
Protocol methods for modules that don't exist.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PackDefinition:
    code: str
    version: str
    jurisdiction_codes: tuple[str, ...]
    # Not yet backed by a seeded governance.rights_profile row for anything
    # other than platform.reference_data (see reference.service) — a real
    # per-vendor rights profile for licensed market data lands in P1 week 7
    # alongside the first connector.
    default_rights_profile_code: str
    capability_codes: tuple[str, ...] = ()
    connector_codes: tuple[str, ...] = field(default_factory=tuple)
    calculation_spec_codes: tuple[str, ...] = field(default_factory=tuple)


class DuplicatePackError(ValueError):
    """Raised by PackRegistry.register on a code collision — packs are
    keyed by code, and a silent overwrite would let a second pack quietly
    replace an earlier one's definition."""


class PackRegistry:
    """Deliberately NOT a module-level singleton mutated at import time —
    that would leak registered packs across tests. Callers get a fresh
    registry and populate it explicitly (see register_default_packs), or
    the app wires one instance into app.state at startup.
    """

    def __init__(self) -> None:
        self._packs: dict[str, PackDefinition] = {}

    def register(self, pack: PackDefinition) -> None:
        if pack.code in self._packs:
            raise DuplicatePackError(f"pack already registered: {pack.code}")
        self._packs[pack.code] = pack

    def get(self, code: str) -> PackDefinition | None:
        return self._packs.get(code)

    def all(self) -> tuple[PackDefinition, ...]:
        return tuple(self._packs.values())


# The first (still-manifest-only) pack instance — P1 populates its
# connectors and calculation spec as those modules come online; for now
# this only pins the shape.
UK_GILTS_PACK = PackDefinition(
    code="uk-gilts",
    version="0.1.0",
    jurisdiction_codes=("GB",),
    default_rights_profile_code="uk-dmo.gilts",
    capability_codes=("reference.issuers.read", "reference.instruments.read"),
    connector_codes=("uk-dmo.gilts.reference", "uk-dmo.gilts.price"),
    calculation_spec_codes=("gilt_price_yield_v1",),
)


def register_default_packs(registry: PackRegistry) -> None:
    """Registers every pack currently known to the platform. Called once at
    app startup (see app.main.create_app) — NOT called implicitly by
    importing this module, so a fresh PackRegistry() elsewhere (tests, a
    future CLI) starts genuinely empty rather than inheriting platform
    defaults it didn't ask for.
    """
    registry.register(UK_GILTS_PACK)
