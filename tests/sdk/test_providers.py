from __future__ import annotations

import dependency_injector.providers as dip
import pytest

from redsun.virtual import ProviderKey, VirtualContainer


class Wanted:
    def __init__(self, tag: str = "") -> None:
        self.tag = tag


class Unrelated: ...


WANTED: ProviderKey[Wanted] = dip.Dependency(instance_of=Wanted)
OTHER: ProviderKey[Wanted] = dip.Dependency(instance_of=Wanted)


def test_provide_and_require_round_trip() -> None:
    """A bound key resolves to the object that was provided."""
    container = VirtualContainer()
    value = Wanted("a")

    container.provide(WANTED, value)

    assert container.require(WANTED) is value
    assert container.try_require(WANTED) is value


@pytest.mark.parametrize("key", [WANTED, OTHER])
def test_unbound_key_is_absent(key: ProviderKey[Wanted]) -> None:
    """An unbound key raises from require and is None from try_require."""
    container = VirtualContainer()

    assert container.try_require(key) is None
    with pytest.raises(KeyError, match="nothing provided"):
        container.require(key)


def test_wrong_type_is_rejected_at_provide() -> None:
    """The key's instance_of is enforced where the value is bound."""
    container = VirtualContainer()

    # mypy already rejects this call: the key carries T, so the mismatch is a
    # type error before it is a runtime one
    with pytest.raises(TypeError, match="not an instance of Wanted"):
        container.provide(WANTED, Unrelated())  # type: ignore[misc]


def test_rebinding_replaces_the_value() -> None:
    """The last value bound to a key wins."""
    container = VirtualContainer()
    container.provide(WANTED, Wanted("first"))

    container.provide(WANTED, Wanted("second"))

    assert container.require(WANTED).tag == "second"


def test_bindings_do_not_leak_between_containers() -> None:
    """A key is a name, not storage: each container holds its own binding."""
    first, second = VirtualContainer(), VirtualContainer()

    first.provide(WANTED, Wanted("first"))
    second.provide(WANTED, Wanted("second"))

    assert first.require(WANTED).tag == "first"
    assert second.require(WANTED).tag == "second"
    assert VirtualContainer().try_require(WANTED) is None
