"""Tests for describing the keys a plugin's components take."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redsun import Session
from redsun.catalog import CatalogAddress
from redsun.compute._pool import PoolExecutor
from redsun.injection import Registry
from redsun.injection._registry import SESSION
from redsun.session._base import HELD

if TYPE_CHECKING:
    from collections.abc import Callable


def test_held_names_every_type_the_session_holds_itself() -> None:
    """Fail when the session registers a type under its own name that `HELD` misses."""
    seen: set[object] = set()

    class Recording(Registry):
        def register(
            self, key: object, factory: Callable[[], object], *, owner: str
        ) -> None:
            if owner == SESSION:
                seen.add(key)
            super().register(key, factory, owner=owner)

    class Empty(Session):
        def make_registry(self) -> Registry:
            return Recording()

    session = Empty({"session": "held"})
    session.build()
    session.shutdown()

    executors = {
        key for key in seen if isinstance(key, type) and issubclass(key, PoolExecutor)
    }
    assert seen - executors <= set(HELD)
    assert set(HELD) - seen <= {CatalogAddress}
