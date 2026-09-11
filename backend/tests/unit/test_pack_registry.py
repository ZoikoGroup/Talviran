import pytest

from app.modules.reference.pack import (
    UK_GILTS_PACK,
    DuplicatePackError,
    PackDefinition,
    PackRegistry,
    register_default_packs,
)


def test_register_and_get() -> None:
    registry = PackRegistry()
    pack = PackDefinition(
        code="test-pack",
        version="1.0.0",
        jurisdiction_codes=("GB",),
        default_rights_profile_code="test.profile",
    )

    registry.register(pack)

    assert registry.get("test-pack") is pack
    assert registry.get("does-not-exist") is None


def test_duplicate_code_raises() -> None:
    registry = PackRegistry()
    pack = PackDefinition(
        code="test-pack",
        version="1.0.0",
        jurisdiction_codes=("GB",),
        default_rights_profile_code="test.profile",
    )
    registry.register(pack)

    with pytest.raises(DuplicatePackError):
        registry.register(pack)


def test_all_returns_every_registered_pack() -> None:
    registry = PackRegistry()
    pack_a = PackDefinition(
        code="a", version="1.0.0", jurisdiction_codes=("GB",), default_rights_profile_code="p"
    )
    pack_b = PackDefinition(
        code="b", version="1.0.0", jurisdiction_codes=("US",), default_rights_profile_code="p"
    )
    registry.register(pack_a)
    registry.register(pack_b)

    assert set(registry.all()) == {pack_a, pack_b}


def test_fresh_registry_starts_empty() -> None:
    # Guards against the exact bug register_default_packs is designed to
    # avoid: importing app.modules.reference.pack must never implicitly
    # populate a shared registry that leaks state between tests/callers.
    registry = PackRegistry()
    assert registry.all() == ()


def test_register_default_packs_includes_uk_gilts() -> None:
    registry = PackRegistry()
    register_default_packs(registry)

    pack = registry.get("uk-gilts")
    assert pack is UK_GILTS_PACK
    assert pack.jurisdiction_codes == ("GB",)
    assert "reference.issuers.read" in pack.capability_codes
    assert "reference.instruments.read" in pack.capability_codes
