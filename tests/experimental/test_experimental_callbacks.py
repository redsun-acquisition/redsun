"""Tests for the bluesky document-callback registry a component is handed."""

from __future__ import annotations

from typing import Any

import pytest
from event_model import DocumentRouter
from event_model.documents import Document

from redsun.experimental import BlueskyCallbackRegistry
from redsun.experimental.registry._builtins import validate_callback


class Recorder:
    """A callback of the ordinary shape, callable as ``(name, doc)``."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.seen: list[str] = []

    def __call__(self, name: str, doc: Document) -> None:
        self.seen.append(name)


class Router(DocumentRouter):
    """A callback that is a document router rather than a plain callable."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class WrongShape:
    """A callback taking one argument where two are delivered."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, name: str) -> None: ...


def _registry(*, sealed: bool = True) -> tuple[BlueskyCallbackRegistry, dict[str, Any]]:
    """Return a registry over a fresh mapping, and the mapping behind it."""
    holder: dict[str, Any] = {}
    return BlueskyCallbackRegistry(holder, lambda: sealed), holder


def test_a_component_registers_itself_under_its_own_name() -> None:
    registry, holder = _registry()
    recorder = Recorder("images")

    registry.register(recorder)

    assert holder == {"images": recorder}


def test_a_key_may_be_given_instead_of_the_name() -> None:
    """Two registrations from one component need two keys."""
    registry, holder = _registry()
    recorder = Recorder("images")

    registry.register(recorder, name="primary")

    assert holder == {"primary": recorder}


def test_several_callbacks_arrive_under_their_own_keys() -> None:
    """The owner is not registered itself when it names a map."""
    registry, holder = _registry()
    owner, first, second = Recorder("owner"), Recorder("a"), Recorder("b")

    registry.register(owner, callback_map={"raw": first, "processed": second})

    assert holder == {"raw": first, "processed": second}


def test_a_document_router_is_accepted_as_it_is() -> None:
    registry, holder = _registry()
    router = Router("router")

    registry.register(router)

    assert holder == {"router": router}


def test_something_that_cannot_be_called_is_refused() -> None:
    with pytest.raises(TypeError, match="is not callable"):
        validate_callback(object())


def test_a_callback_of_the_wrong_shape_is_refused() -> None:
    """It would fail on the first document, long after registration."""
    with pytest.raises(TypeError, match="not compatible"):
        validate_callback(WrongShape("narrow"))


def test_the_registry_reads_as_the_mapping_it_claims_to_be() -> None:
    registry, _ = _registry()
    recorder = Recorder("images")
    registry.register(recorder)

    assert len(registry) == 1
    assert list(registry) == ["images"]
    assert registry["images"] is recorder


def test_reading_before_the_build_is_sealed_is_refused() -> None:
    """The components after this one have registered nothing yet."""
    registry, _ = _registry(sealed=False)
    registry.register(Recorder("images"))

    with pytest.raises(LookupError):
        len(registry)


def test_registering_is_allowed_before_the_build_is_sealed() -> None:
    """Registration is what a component does while it is being built."""
    registry, holder = _registry(sealed=False)

    registry.register(Recorder("images"))

    assert set(holder) == {"images"}


def test_the_repr_says_whether_it_can_be_read_yet() -> None:
    pending, _ = _registry(sealed=False)
    live, _ = _registry()
    live.register(Recorder("images"))

    assert "pending, 0 registered" in repr(pending)
    assert "live, 1 registered" in repr(live)


def test_the_view_is_live_rather_than_a_copy() -> None:
    """A component holds it and reads what components built after it added."""
    registry, holder = _registry()
    registry.register(Recorder("first"))

    holder["later"] = Recorder("later")

    assert set(registry) == {"first", "later"}
