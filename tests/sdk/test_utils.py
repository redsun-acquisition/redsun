from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from psygnal import Signal

from redsun.utils import find_signals
from redsun.utils.descriptors import parse_key, parse_map_key

if TYPE_CHECKING:
    from redsun.virtual import VirtualContainer


class _OwnerA:
    sig_move = Signal(float)
    sig_stop = Signal()

    def __init__(self) -> None:
        self.name = "owner_a"


class _OwnerB:
    sig_config = Signal(str)

    def __init__(self) -> None:
        self.name = "owner_b"


def test_find_signals_across_owners(bus: VirtualContainer) -> None:
    owner_a, owner_b = _OwnerA(), _OwnerB()
    bus.register_signals(owner_a)
    bus.register_signals(owner_b)

    found = find_signals(bus, ["sig_move", "sig_config", "sig_missing"])
    assert set(found.keys()) == {"sig_move", "sig_config"}
    assert found["sig_move"] is owner_a.sig_move
    assert found["sig_config"] is owner_b.sig_config


def test_find_signals_stops_after_all_found(bus: VirtualContainer) -> None:
    bus.register_signals(_OwnerA())
    found = find_signals(bus, ["sig_move", "sig_stop"])
    assert set(found.keys()) == {"sig_move", "sig_stop"}


def test_parse_key_round_trip() -> None:
    assert parse_key("det-roi-x") == ("det", "roi-x")
    with pytest.raises(ValueError, match="does not conform"):
        parse_key("nohyphen")


def test_parse_map_key() -> None:
    assert parse_map_key("stage-axis-x", "axis") == ("stage", "axis", "x")
    with pytest.raises(ValueError, match="does not conform"):
        parse_map_key("stage-x", "axis")
    with pytest.raises(ValueError, match="does not conform"):
        parse_map_key("stage-motor-x", "axis")


def test_find_signals_owner_scoped(bus: VirtualContainer) -> None:
    """Same signal name on two owners: the owner name is what discerns them."""

    class _OwnerC:
        sig_move = Signal(float)

        def __init__(self) -> None:
            self.name = "owner_c"

    owner_a, owner_c = _OwnerA(), _OwnerC()
    bus.register_signals(owner_a)
    bus.register_signals(owner_c)

    from_a = find_signals(bus, ["sig_move"], owner="owner_a")
    from_c = find_signals(bus, ["sig_move"], owner="owner_c")
    assert from_a["sig_move"] is owner_a.sig_move
    assert from_c["sig_move"] is owner_c.sig_move
    assert from_a["sig_move"] is not from_c["sig_move"]


def test_find_signals_unknown_owner_returns_empty(bus: VirtualContainer) -> None:
    bus.register_signals(_OwnerA())
    assert find_signals(bus, ["sig_move"], owner="ghost") == {}
