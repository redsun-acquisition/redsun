import logging

import pytest

from event_model import DocumentRouter
from redsun.virtual import IsInjectable, IsProvider, Signal, VirtualContainer

logger = logging.getLogger("redsun")
logger.setLevel(logging.DEBUG)


class MockRouter(DocumentRouter):
    """DocumentRouter subclass — the primary callback form."""

    name = "mock_router"

    def __init__(self) -> None:
        super().__init__()

    def event(self, doc: dict) -> None:  # type: ignore[override]
        logger.debug("MockRouter received event document")

    def start(self, doc: dict) -> None:  # type: ignore[override]
        logger.debug("MockRouter received start document")

    def stop(self, doc: dict) -> None:  # type: ignore[override]
        logger.debug("MockRouter received stop document")

    def descriptor(self, doc: dict) -> None:  # type: ignore[override]
        logger.debug("MockRouter received descriptor document")


class MockCallable:
    """Non-router callable with the correct (str, Document) signature."""

    name = "mock_callable"

    def __call__(self, name: str, doc: dict) -> None:
        logger.debug(f"MockCallable received {name} document")


class MockBadCallable:
    """Callable whose signature does not match (str, Document)."""

    name = "mock_bad_callable"

    def __call__(self, name: str) -> None:  # missing doc argument
        pass


class MockNonCallable:
    """Object that is not callable at all."""

    name = "mock_non_callable"


def test_virtual_container_no_object(bus: VirtualContainer) -> None:
    """Test that accessing a non-existent signal key raises KeyError."""
    with pytest.raises(KeyError):
        bus.signals["MockOwner"]


def test_virtual_container_psygnal_connection(bus: VirtualContainer) -> None:
    """Tests signal registration and cross-component connection via VirtualContainer."""

    class FirstMockOwner(IsProvider):
        sigFirstSignal = Signal(int)

        def __init__(self, container: VirtualContainer) -> None:
            self.container = container
            self.name = "FirstMockOwner"

        def register_providers(self, container: VirtualContainer) -> None:
            container.register_signals(self)

        def second_to_first(self, x: int) -> None:
            assert x == 5

    class SecondMockOwner(IsInjectable):
        sigSecondSignal = Signal(int)

        def __init__(self, container: VirtualContainer) -> None:
            self.container = container
            self.name = "SecondMockOwner"

        def inject_dependencies(self, container: VirtualContainer) -> None:
            container.register_signals(self)
            container.signals["FirstMockOwner"]["sigFirstSignal"].connect(
                self.first_to_second
            )

        def first_to_second(self, x: int) -> None:
            assert x == 5

    first_owner = FirstMockOwner(bus)
    second_owner = SecondMockOwner(bus)

    # provider registers its own signals first
    first_owner.register_providers(bus)
    # injectable registers its signals and connects to provider's signals
    second_owner.inject_dependencies(bus)

    # first owner can now connect to second owner's signal
    bus.signals["SecondMockOwner"]["sigSecondSignal"].connect(
        first_owner.second_to_first
    )

    assert "FirstMockOwner" in bus.signals
    assert "SecondMockOwner" in bus.signals

    first_owner.sigFirstSignal.emit(5)
    second_owner.sigSecondSignal.emit(5)


def test_virtual_container_psygnal_connection_only(bus: VirtualContainer) -> None:
    """Test 'register_signals' using the 'only' parameter."""

    def callback(x: int) -> None:
        assert x == 5

    class MockOwner:
        sigSignalOne = Signal(int)
        sigSignalTwo = Signal(int)

        @property
        def name(self) -> str:
            return "MockOwner"

    owner = MockOwner()

    bus.register_signals(owner, only=["sigSignalOne"])

    assert "MockOwner" in bus.signals
    assert len(bus.signals["MockOwner"]) == 1
    assert "sigSignalOne" in bus.signals["MockOwner"]
    assert "sigSignalTwo" not in bus.signals["MockOwner"]

    bus.signals["MockOwner"]["sigSignalOne"].connect(callback)
    owner.sigSignalOne.emit(5)


def test_register_callbacks_document_router(bus: VirtualContainer) -> None:
    """DocumentRouter subclass is registered under owner.name."""
    router = MockRouter()
    bus.register_callbacks(router)
    assert "mock_router" in bus.callbacks
    assert bus.callbacks["mock_router"] is router


def test_register_callbacks_callable_object(bus: VirtualContainer) -> None:
    """Object with a compatible __call__ signature is accepted."""
    cb = MockCallable()
    bus.register_callbacks(cb)
    assert "mock_callable" in bus.callbacks
    assert bus.callbacks["mock_callable"] is cb


def test_register_callbacks_name_override(bus: VirtualContainer) -> None:
    """Explicit name parameter is used as registry key instead of owner.name."""
    router = MockRouter()
    bus.register_callbacks(router, name="custom_key")
    assert "custom_key" in bus.callbacks
    assert bus.callbacks["custom_key"] is router


def test_register_callbacks_rejects_non_callable(bus: VirtualContainer) -> None:
    """Non-callable owner that is not a DocumentRouter raises TypeError."""
    with pytest.raises(TypeError, match="not callable"):
        bus.register_callbacks(MockNonCallable())


def test_register_callbacks_rejects_wrong_signature(bus: VirtualContainer) -> None:
    """Callable owner with wrong __call__ signature raises TypeError."""
    with pytest.raises(TypeError, match="not compatible"):
        bus.register_callbacks(MockBadCallable())


def test_register_callbacks_callback_map(bus: VirtualContainer) -> None:
    """callback_map registers multiple callbacks under independent keys."""
    router = MockRouter()
    cb = MockCallable()

    bus.register_callbacks(
        router,
        callback_map={"router_key": router, "callable_key": cb},
    )

    assert "router_key" in bus.callbacks
    assert "callable_key" in bus.callbacks
    assert bus.callbacks["router_key"] is router
    assert bus.callbacks["callable_key"] is cb


def test_register_callbacks_callback_map_rejects_invalid(bus: VirtualContainer) -> None:
    """callback_map validates each entry and raises TypeError on bad values."""
    router = MockRouter()
    with pytest.raises(TypeError):
        bus.register_callbacks(
            router,
            callback_map={"good": router, "bad": MockBadCallable()},
        )


def test_is_provider_protocol(bus: VirtualContainer) -> None:
    """Test IsProvider structural protocol check."""

    class MyPresenter:
        def register_providers(self, container: VirtualContainer) -> None:
            pass

    p = MyPresenter()
    assert isinstance(p, IsProvider)
    assert issubclass(MyPresenter, IsProvider)


def test_is_injectable_protocol(bus: VirtualContainer) -> None:
    """Test IsInjectable structural protocol check."""

    class MyView:
        def inject_dependencies(self, container: VirtualContainer) -> None:
            pass

    v = MyView()
    assert isinstance(v, IsInjectable)
    assert issubclass(MyView, IsInjectable)


def test_register_signals_all_signals_survive(bus: VirtualContainer) -> None:
    """All signals on a class are registered when register_signals is called.

    Regression test: previously register_signals called add_kwargs inside a
    per-signal loop, causing each call to overwrite the previous entry for the
    same owner key in the Factory kwargs store.  Only the last signal survived.
    """

    class MultiSignalOwner:
        sigFirst = Signal(int)
        sigSecond = Signal(str)
        sigThird = Signal()

        @property
        def name(self) -> str:
            return "MultiSignalOwner"

    owner = MultiSignalOwner()
    bus.register_signals(owner)

    assert "MultiSignalOwner" in bus.signals
    registered = bus.signals["MultiSignalOwner"]
    assert "sigFirst" in registered
    assert "sigSecond" in registered
    assert "sigThird" in registered
    assert len(registered) == 3


def test_virtual_container_configuration(bus: VirtualContainer) -> None:
    """Test that configuration can be set and read back from VirtualContainer."""

    bus._set_configuration(
        {"schema_version": 1.0, "session": "redsun", "frontend": "unknown"}
    )

    assert bus.session == "redsun"
    assert bus.schema_version == 1.0
    assert bus.frontend == "unknown"
    assert bus.metadata == {}

    bus._config.reset()

    bus._set_configuration(
        {
            "schema_version": 2.0,
            "session": "test-session",
            "frontend": "pyqt",
            "metadata": {"key": "value"},
        }
    )

    assert bus.schema_version == 2.0
    assert bus.session == "test-session"
    assert bus.frontend == "pyqt"
    assert bus.metadata == {"key": "value"}

