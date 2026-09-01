"""Tests for the experimental dishka-backed container."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, NewType

import pydantic
import pytest
from ophyd_async.core import Device
from psygnal import Signal

from redsun.experimental import (
    Alias,
    AppContainer,
    AsDevice,
    AsPresenter,
    AsView,
    BlueskyCallbackRegistry,
    Declare,
    DeviceMapping,
    FromConfig,
    Frontend,
    Placement,
    VirtualContainer,
    provides,
    slot,
)
from redsun.experimental.containers._declarations import (
    Layer,
    check,
    leads_with_name,
)
from redsun.experimental.containers._factories import (
    injectable,
    optional_arg,
    synthesize,
)

if TYPE_CHECKING:
    from pathlib import Path

Readings = NewType("Readings", "dict[str, float]")
Descriptions = NewType("Descriptions", "dict[str, str]")
Missing = NewType("Missing", "dict[str, int]")


class Stage(Device):
    """Device with a configured keyword argument."""

    def __init__(self, name: str, /, axis: str = "X") -> None:
        super().__init__(name=name)
        self.axis = axis


class Ctrl:
    """Presenter sharing two values derived from its devices."""

    sig_moved = Signal(str)

    def __init__(self, name: str, /, devices: DeviceMapping, gain: float = 1.0) -> None:
        self.name = name
        self.devices = devices
        self.gain = gain

    @provides
    def readings(self) -> Readings:
        return Readings({name: self.gain for name in self.devices})

    @provides
    def descriptions(self) -> Descriptions:
        return Descriptions(
            {
                name: type(d).__name__
                for name in self.devices
                for d in [self.devices[name]]
            }
        )

    @slot
    def on_move(self, where: str) -> None:
        self.moved = where


@dataclass(frozen=True)
class Panel(Placement):
    """A placement the toy frontend below attaches."""

    side: str


@dataclass(frozen=True)
class Elsewhere(Placement):
    """A placement no frontend attaches."""


class Attachable:
    """The type Toy demands of a view, standing in for a toolkit class."""


class Attached(Attachable):
    """A view Toy can attach."""

    placement: Placement = Panel("left")

    def __init__(self, name: str, /) -> None:
        self.name = name


class Unattachable:
    """A view asking for a placement Toy attaches, without being what it demands."""

    placement: Placement = Panel("left")

    def __init__(self, name: str, /) -> None:
        self.name = name


class Toy(Frontend):
    """A frontend that attaches one placement, standing in for a real one."""

    requires: ClassVar[Mapping[type[Placement], type]] = {Panel: Attachable}


class Widget:
    """View consuming one required and one optional shared value."""

    placement: Placement = Panel("left")

    def __init__(
        self,
        name: str,
        /,
        callbacks: BlueskyCallbackRegistry,
        readings: Readings,
        missing: Missing | None = None,
        label: str = "",
    ) -> None:
        self.name = name
        self.callbacks = callbacks
        self.readings = readings
        self.missing = missing
        self.label = label

    @slot
    def refresh(self, where: str) -> None:
        self.seen = where


class Late:
    """Presenter reading a registry that fills after it is built."""

    def __init__(self, name: str, /, callbacks: BlueskyCallbackRegistry) -> None:
        self.name = name
        self.callbacks = callbacks

    def known(self) -> dict[str, Any]:
        return dict(self.callbacks)


class Registrar:
    """Presenter that registers a document callback while it is built."""

    def __init__(self, name: str, /, callbacks: BlueskyCallbackRegistry) -> None:
        self.name = name
        self.closed = False
        callbacks.register(self, name=name)

    def __call__(self, name: str, doc: Any) -> None: ...

    def shutdown(self) -> None:
        self.closed = True


class Tunable:
    """Presenter with two defaulted parameters, one of which is provided."""

    def __init__(
        self, name: str, /, step: float = 1.5, readings: Readings | None = None
    ) -> None:
        self.name = name
        self.step = step
        self.readings = readings


class Eager:
    """Presenter copying the live registry while it is still filling."""

    def __init__(self, name: str, /, callbacks: BlueskyCallbackRegistry) -> None:
        self.name = name
        self.copy = dict(callbacks)


teardown_order: list[str] = []


class Recorder:
    """Presenter nothing depends on."""

    def __init__(self, name: str, /) -> None:
        self.name = name

    def shutdown(self) -> None:
        teardown_order.append(self.name)


class Dependent:
    """Presenter built from `Recorder`, so it exists only after one does."""

    def __init__(self, name: str, /, other: Recorder) -> None:
        self.name = name
        self.other = other

    def shutdown(self) -> None:
        teardown_order.append(self.name)


class EagerApp(AppContainer):
    eager: AsPresenter[Eager]


class OrderedApp(AppContainer):
    second: Annotated[AsPresenter[Dependent], Alias("second")]
    first: Annotated[AsPresenter[Recorder], Alias("first")]


class App(AppContainer):
    config: ClassVar[Mapping[str, Any]] = {
        "name": "test-session",
        "devices": {"stage": {"axis": "Z"}},
        "presenters": {"ctrl": {"gain": 2.0}},
        "views": {"widget": {"label": "from-config"}},
    }

    motor: Annotated[AsDevice[Stage], FromConfig("stage")]
    ctrl: AsPresenter[Ctrl]
    registrar: AsPresenter[Registrar]
    late: AsPresenter[Late]
    tunable: AsPresenter[Tunable]
    widget: Annotated[AsView[Widget], Declare(label="inline")]


class Nameless:
    """Presenter taking the name the framework hands it and dropping it."""

    def __init__(self, name: str, /) -> None:
        self.gain = 1.0


class NamelessView(Nameless, Attachable):
    """View doing the same, reached through the placement half of the protocol."""

    placement: Placement = Panel("left")


class NamelessApp(AppContainer):
    __slots__ = ()

    ctrl: AsPresenter[Nameless]


class NamelessViewApp(AppContainer):
    __slots__ = ()

    frontend = Toy
    panel: AsView[NamelessView]


class Deferred:
    """View answering its placement from a property rather than the class."""

    def __init__(self, name: str, /) -> None:
        self.name = name

    @property
    def placement(self) -> Placement:
        return Elsewhere()


class DeferredApp(AppContainer):
    __slots__ = ()

    frontend = Toy

    stray: AsView[Deferred]


class ToyApp(AppContainer):
    __slots__ = ()

    frontend = Toy


class InheritsToy(ToyApp):
    __slots__ = ()


@pytest.fixture
def app() -> Any:
    container = App().build()
    yield container
    container.shutdown()


def test_build_resolves_every_declaration(app: App) -> None:
    """Components come up, typed attributes reach them, devices are built."""
    assert app.is_built
    assert isinstance(app.ctrl, Ctrl)
    assert isinstance(app.widget, Widget)
    assert isinstance(app.motor, Stage)
    assert app.devices == {"motor": app.motor}
    assert app.motor.axis == "Z"


def test_config_supplies_kwargs_and_inline_overrides(app: App) -> None:
    """The attribute name is the config key, and Declare wins over the file."""
    assert app.ctrl.gain == 2.0
    assert app.widget.label == "inline"
    assert app.virtual_container.name == "test-session"


def test_shared_value_is_bound_to_its_owner(app: App) -> None:
    """A @provides method is called on the built component that declares it."""
    assert app.widget.readings == {"motor": 2.0}


def test_absent_optional_is_none(app: App) -> None:
    """Nothing provides Missing, so the parameter is None rather than an error."""
    assert app.widget.missing is None


def test_default_applies_when_nothing_provides_the_type(app: App) -> None:
    """A parameter the session says nothing about keeps its own default."""
    assert app.tunable.step == 1.5


def test_default_is_overridden_by_what_the_session_provides(app: App) -> None:
    """A defaulted parameter is still filled when the type is available."""
    assert app.tunable.readings == {"motor": 2.0}


def test_framework_objects_are_injectable(app: App) -> None:
    """The device map and the callback registry are ordinary dependencies."""
    assert dict(app.ctrl.devices) == {"motor": app.motor}
    assert app.widget.callbacks is app.late.callbacks


class WantsTheContainer:
    def __init__(self, name: str, /, bus: VirtualContainer) -> None:
        self.name = name
        self.bus = bus


class LocatorApp(AppContainer):
    greedy: AsPresenter[WantsTheContainer]


def test_the_container_itself_is_not_injectable() -> None:
    """A component cannot ask for the whole bus and help itself from it.

    The exception type belongs to whatever resolves the graph, so only the
    name of the key it could not find is pinned.
    """
    with pytest.raises(Exception, match="VirtualContainer"):
        LocatorApp().build()


def test_live_registry_is_complete_after_the_build(app: App) -> None:
    """The view a component was given reflects what every component registered."""
    assert app.late.known() == {"registrar": app.registrar}


def test_live_registry_refuses_to_be_read_early() -> None:
    """Reading during construction would answer with a half-filled registry."""
    with pytest.raises(LookupError, match="not complete until every component"):
        EagerApp().build()


def test_shutdown_finalizes_components_in_reverse_build_order() -> None:
    """One owner runs every teardown, and the graph decides the order."""
    teardown_order.clear()
    container = OrderedApp().build()
    container.shutdown()
    assert teardown_order == ["second", "first"]


def test_component_shutdown_runs_without_being_asked(app: App) -> None:
    """A component declaring shutdown needs no registration of its own."""
    registrar = app.registrar
    assert not registrar.closed
    app.shutdown()
    assert registrar.closed


def test_signals_are_registered_without_being_asked(app: App) -> None:
    """register_signals runs for every built component."""
    assert "sig_moved" in app.virtual_container.signals["ctrl"]


def test_unknown_attribute_raises_attribute_error(app: App) -> None:
    with pytest.raises(AttributeError, match="declares no component"):
        _ = app.nonexistent


def test_rebuild_is_a_no_op(app: App) -> None:
    first = app.ctrl
    app.build()
    assert app.ctrl is first


def test_shutdown_releases_and_allows_gc() -> None:
    container = App().build()
    container.shutdown()
    assert not container.is_built


class Duplicated:
    def __init__(self, name: str, /) -> None:
        self.name = name

    @provides
    def value(self) -> Readings:
        return Readings({})


class TwoOwners(AppContainer):
    first: Annotated[AsPresenter[Duplicated], Alias("first")]
    second: Annotated[AsPresenter[Duplicated], Alias("second")]


def test_two_components_sharing_one_type_is_refused() -> None:
    """The message names both, which resolution-time failure could not."""
    with pytest.raises(TypeError, match="both share"):
        TwoOwners().build()


ViewerModel = NewType("ViewerModel", "dict[str, str]")


class Displaying:
    """A view owning something another view of the same layer wants."""

    placement: Placement = Panel("left")

    def __init__(self, name: str, /) -> None:
        self.name = name
        self._viewer = ViewerModel({})

    @provides
    def viewer(self) -> ViewerModel:
        return self._viewer


class Controlling:
    """A view reaching for what a view built beside it owns."""

    placement: Placement = Panel("left")

    def __init__(self, name: str, /, viewer: ViewerModel) -> None:
        self.name = name
        self.viewer = viewer


class WatchingAView:
    """A presenter naming the class of a view."""

    def __init__(self, name: str, /, display: Displaying) -> None:
        self.name = name
        self.display = display


class WantingWhatAViewOwns:
    """A presenter asking for a type only a view shares."""

    def __init__(self, name: str, /, viewer: ViewerModel) -> None:
        self.name = name


class HoldingAPresenter:
    """A view naming the class of a presenter, which is the allowed direction."""

    placement: Placement = Panel("left")

    def __init__(self, name: str, /, ctrl: Recorder) -> None:
        self.name = name
        self.ctrl = ctrl


class SameLayerApp(AppContainer):
    display: AsView[Displaying]
    control: AsView[Controlling]


class PresenterOnAViewClass(AppContainer):
    watcher: AsPresenter[WatchingAView]
    display: AsView[Displaying]


class PresenterOnAViewValue(AppContainer):
    wanting: AsPresenter[WantingWhatAViewOwns]
    display: AsView[Displaying]


class ViewOnAPresenter(AppContainer):
    recorder: AsPresenter[Recorder]
    holder: AsView[HoldingAPresenter]


def test_two_views_of_one_layer_may_share() -> None:
    """The owner is built first because the graph says so, not by hand."""
    app = SameLayerApp().build()
    try:
        assert app.control.viewer is app.display.viewer()
    finally:
        app.shutdown()


def test_a_view_may_depend_on_a_presenter() -> None:
    """A view is built after a presenter, so naming one is the allowed direction."""
    app = ViewOnAPresenter().build()
    try:
        assert app.holder.ctrl is app.recorder
    finally:
        app.shutdown()


@pytest.mark.parametrize(
    ("app", "match"),
    [
        (PresenterOnAViewClass, "'display'"),
        (PresenterOnAViewValue, "'display'"),
    ],
)
def test_a_presenter_depending_on_a_view_is_refused(
    app: type[AppContainer], match: str
) -> None:
    """Naming the class or a type it shares is the same backwards edge."""
    with pytest.raises(TypeError, match="is built before a view"):
        app().build()
    with pytest.raises(TypeError, match=match):
        app().build()


class Unannotated:
    def __init__(self, name: str, /, thing) -> None:  # type: ignore[no-untyped-def]
        self.name = name


class BadApp(AppContainer):
    broken: AsPresenter[Unannotated]


def test_unannotated_parameter_is_refused() -> None:
    with pytest.raises(TypeError, match="has no annotation"):
        BadApp().build()


@pytest.mark.parametrize(
    ("target", "declared"),
    [
        (Stage, Layer.DEVICE),
        (Ctrl, Layer.PRESENTER),
        (Widget, Layer.VIEW),
    ],
)
def test_a_class_may_be_declared_in_the_layer_it_belongs_to(
    target: type, declared: Layer
) -> None:
    assert check(target, declared, "somewhere") is target


class VariadicDevice(Device):
    """A device whose constructor would also fail the name check."""

    def __init__(self, *args: object) -> None: ...


@pytest.mark.parametrize(
    ("target", "declared", "match"),
    [
        (Stage, Layer.PRESENTER, "is an 'ophyd_async.core.Device'"),
        (Stage, Layer.VIEW, "is an 'ophyd_async.core.Device'"),
        (VariadicDevice, Layer.PRESENTER, "is an 'ophyd_async.core.Device'"),
        (Ctrl, Layer.DEVICE, "does not subclass 'ophyd_async.core.Device'"),
        (int, Layer.PRESENTER, "does not take 'name'"),
        ("not a type", Layer.VIEW, "is not a class"),
        (Ctrl, Layer.VIEW, "declares no 'placement'"),
        (Widget, Layer.PRESENTER, "declares a 'placement'"),
    ],
)
def test_a_class_declared_in_the_wrong_layer_is_refused(
    target: object, declared: Layer, match: str
) -> None:
    """A placement is what separates the two component layers, both ways."""
    with pytest.raises(TypeError, match=match):
        check(target, declared, "somewhere")


@pytest.mark.parametrize(
    ("view", "frontend", "placement"),
    [
        (Attached, Toy, Panel("left")),
        (Attached("view"), Toy, Panel("left")),
        (Unattachable, Frontend, Panel("left")),
        (Unattachable, Frontend, Elsewhere()),
    ],
)
def test_a_frontend_accepts_what_it_attaches(
    view: type | object, frontend: type[Frontend], placement: Placement
) -> None:
    """A class and an instance answer alike, and no toolkit constrains nothing."""
    frontend.check_placement(view, placement, "somewhere")


@pytest.mark.parametrize(
    ("view", "placement", "match"),
    [
        (Attached, Elsewhere(), "'Elsewhere', which Toy does not attach"),
        (
            Unattachable,
            Panel("left"),
            "needs a Attachable, but Unattachable is not one",
        ),
    ],
)
def test_a_frontend_refuses_what_it_cannot_attach(
    view: type, placement: Placement, match: str
) -> None:
    """Either half of the pairing can be wrong, and each says which."""
    with pytest.raises(TypeError, match=match):
        Toy.check_placement(view, placement, "somewhere")


class Stray:
    """A view asking for a placement Toy does not attach."""

    placement: Placement = Elsewhere()

    def __init__(self, name: str, /) -> None:
        self.name = name


@pytest.mark.parametrize(
    ("target", "match"),
    [
        (Stray, "does not attach"),
        (Unattachable, "needs a Attachable"),
    ],
)
def test_a_view_is_refused_at_declaration_for_its_placement(
    target: type, match: str
) -> None:
    """The class answers both halves, so nothing has to be built to find out."""
    with pytest.raises(TypeError, match=match):
        check(target, Layer.VIEW, "somewhere", Toy)


@pytest.mark.parametrize(
    ("app", "protocol"),
    [(NamelessApp, "NamedComponent"), (NamelessViewApp, "AttachableComponent")],
)
def test_a_component_that_drops_its_name_is_refused(
    app: type[AppContainer], protocol: str
) -> None:
    """The constructor is made to take a name; keeping it is the other half."""
    with pytest.raises(TypeError, match=f"does not satisfy {protocol!r}: 'name'"):
        app().build()


def test_a_view_the_frontend_attaches_is_accepted_at_declaration() -> None:
    assert check(Attached, Layer.VIEW, "somewhere", Toy) is Attached


def test_a_view_answering_from_an_instance_is_checked_after_it_is_built() -> None:
    """A placement behind a property is invisible on the class, so build first."""
    assert check(Deferred, Layer.VIEW, "somewhere", Toy) is Deferred
    with pytest.raises(TypeError, match="view 'stray' asks to be attached"):
        DeferredApp().build()


@pytest.mark.parametrize(
    ("container", "expected"),
    [(App, Frontend), (ToyApp, Toy), (InheritsToy, Toy)],
)
def test_the_frontend_comes_from_the_class_it_is_declared_on(
    container: type[AppContainer], expected: type[Frontend]
) -> None:
    assert container.frontend is expected


def test_a_component_shadowing_a_container_attribute_is_refused() -> None:
    """__getattr__ never runs for a name ordinary lookup already answers."""

    class Shadowed(AppContainer):
        __slots__ = ()

        # mypy sees the clash too; the container has to as well
        devices: AsPresenter[Ctrl]  # type: ignore[assignment]

    with pytest.raises(TypeError, match="already an attribute of the container"):
        Shadowed().build()


def test_an_annotation_without_a_layer_is_an_ordinary_attribute(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A declaration is opt-in, so a container may hold plain attributes."""

    class Plain(AppContainer):
        __slots__ = ()

        threshold: int
        ctrl: AsPresenter[Ctrl]

    app = Plain().build()
    try:
        assert set(app.declarations) == {"ctrl"}
        assert "declares no layer" not in caplog.text
    finally:
        app.shutdown()


def test_a_component_nothing_reaches_is_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A half-finished declaration, or a wiring rule with a typo in the name."""

    class Inert(AppContainer):
        __slots__ = ()

        recorder: AsPresenter[Recorder]

    app = Inert().build()
    try:
        assert (
            "'recorder' shares nothing, asks for nothing and is wired to nothing"
            in caplog.text
        )
    finally:
        app.shutdown()


def test_a_component_another_is_built_from_is_not_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Being injected is being used, though the component asks for nothing itself."""
    app = OrderedApp().build()
    try:
        assert "'first' shares nothing" not in caplog.text
    finally:
        app.shutdown()


def test_a_shared_value_nothing_asks_for_is_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Usually the consumer was renamed or removed while the producer stayed."""
    app = App().build()
    try:
        assert (
            "ctrl.descriptions shares 'Descriptions', which no component asks for"
            in caplog.text
        )
    finally:
        app.shutdown()


def test_a_session_is_named_after_its_class_when_it_says_nothing() -> None:
    """A shared constant would let two unrelated sessions collide silently."""

    class Instrument(AppContainer):
        __slots__ = ()

    app = Instrument().build()
    try:
        assert app.virtual_container.name == "Instrument"
    finally:
        app.shutdown()


def test_a_forgotten_layer_is_reported(caplog: pytest.LogCaptureFixture) -> None:
    """Omitting the marker is silent by design, so a likely component is flagged."""

    class Forgot(AppContainer):
        __slots__ = ()

        ctrl: Ctrl

    app = Forgot().build()
    try:
        assert dict(app.declarations) == {}
        assert "Forgot.ctrl annotates Ctrl but declares no layer" in caplog.text
    finally:
        app.shutdown()


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        (int | None, int),
        (Readings | None, Readings),
        (int, None),
        (int | str, None),
        (int | str | None, None),
    ],
)
def test_optional_arg(hint: Any, expected: Any) -> None:
    assert optional_arg(hint) is expected


def test_injectable_excludes_name_and_config_kwargs() -> None:
    """Identity and configured values are bound, never resolved."""
    assert set(injectable(Ctrl, {})) == {"devices", "gain"}
    assert set(injectable(Ctrl, {"gain": 1.0})) == {"devices"}


def test_synthesize_agrees_with_both_introspection_routes() -> None:
    """Dishka reads the signature and the annotations; they must match."""
    import inspect

    def build(**deps: Any) -> Any:
        return deps

    synthesize(build, {"a": int, "b": str}, Readings, "build_thing")

    signature = inspect.signature(build)
    assert build.__name__ == "build_thing"
    assert list(signature.parameters) == ["a", "b"]
    assert all(
        p.kind is inspect.Parameter.KEYWORD_ONLY for p in signature.parameters.values()
    )
    assert build.__annotations__ == {"a": int, "b": str, "return": Readings}
    assert signature.return_annotation is Readings


class PydanticCtrl(pydantic.BaseModel):
    """Presenter whose fields are keyword-only, as every pydantic model's are."""

    name: str
    devices: DeviceMapping
    gain: float = 2.0

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)


class PydanticApp(AppContainer):
    motor: AsDevice[Stage]
    ctrl: Annotated[AsPresenter[PydanticCtrl], Declare(gain=7.5)]


def test_a_keyword_only_component_is_built() -> None:
    """A pydantic model takes its name as a keyword; the container looks first."""
    app = PydanticApp().build()
    assert app.ctrl.name == "ctrl"
    assert app.ctrl.gain == 7.5
    assert dict(app.ctrl.devices) == {"motor": app.motor}


def test_the_two_constructor_shapes_are_read_alike() -> None:
    """A pydantic model and an ordinary class must not drift apart.

    Their annotations live in different places: an ordinary class states them
    on ``__init__``, a pydantic model only in its synthesized signature.
    """
    assert injectable(PydanticCtrl, {}) == injectable(Ctrl, {})
    assert injectable(PydanticCtrl, {"gain": 1.0}) == injectable(Ctrl, {"gain": 1.0})


class VariadicName:
    def __init__(self, *name: str) -> None: ...


class KeywordName:
    def __init__(self, *, name: str) -> None: ...


@pytest.mark.parametrize(
    ("cls", "accepted"),
    [(Ctrl, True), (PydanticCtrl, True), (KeywordName, True), (VariadicName, False)],
)
def test_a_name_that_cannot_be_passed_is_refused(cls: type, accepted: bool) -> None:
    """A name arriving inside ``*args`` is not a name the component can be built with."""
    assert leads_with_name(cls) is accepted


@dataclass
class DataclassCtrl:
    """Presenter whose annotations live on a generated ``__init__``."""

    name: str
    devices: DeviceMapping
    gain: float = 2.0


@dataclass(kw_only=True)
class KwOnlyCtrl:
    """The stdlib route to a keyword-only constructor."""

    name: str
    devices: DeviceMapping
    gain: float = 2.0


@dataclass(frozen=True, slots=True)
class FrozenCtrl:
    """Frozen and slotted, which change what the class carries at runtime."""

    name: str
    devices: DeviceMapping
    gain: float = 2.0


class DataclassApp(AppContainer):
    motor: AsDevice[Stage]
    ctrl: Annotated[AsPresenter[DataclassCtrl], Declare(gain=7.5)]


class KwOnlyApp(AppContainer):
    motor: AsDevice[Stage]
    ctrl: Annotated[AsPresenter[KwOnlyCtrl], Declare(gain=7.5)]


class FrozenApp(AppContainer):
    motor: AsDevice[Stage]
    ctrl: Annotated[AsPresenter[FrozenCtrl], Declare(gain=7.5)]


@pytest.mark.parametrize("app", [DataclassApp, KwOnlyApp, FrozenApp])
def test_a_dataclass_is_an_ordinary_component(app: type[AppContainer]) -> None:
    """Every dataclass flavour builds, whatever kind its fields become."""
    built = app().build()
    assert built.ctrl.name == "ctrl"
    assert built.ctrl.gain == 7.5
    assert dict(built.ctrl.devices) == {"motor": built.motor}


class Shared(AppContainer):
    """A base holding what every session of one instrument shares."""

    config: ClassVar[Mapping[str, Any]] = {
        "schema_version": 1.0,
        "name": "shared",
        "devices": {"motor": {"axis": "Z"}},
        "presenters": {"ctrl": {"gain": 1.0}},
    }

    motor: AsDevice[Stage]
    ctrl: AsPresenter[Ctrl]


class Layered(Shared):
    """A session laying its own configuration over the base's."""

    config: ClassVar[Mapping[str, Any]] = {
        "name": "layered",
        "presenters": {"ctrl": {"gain": 9.0}},
    }


class Sideways(AppContainer):
    """A second base, so that Shared can be reached by two paths at once."""

    config: ClassVar[Mapping[str, Any]] = {"devices": {"motor": {"axis": "Y"}}}


class Diamond(Layered, Sideways):
    """Inherits from both, and must resolve the two the way Python does."""


def test_a_subclass_layers_over_its_base() -> None:
    """The base holds the instrument, the subclass holds the session."""
    app = Layered().build()
    assert app.virtual_container.name == "layered"
    assert app.ctrl.gain == 9.0
    assert app.motor.axis == "Z"


def test_layering_follows_the_mro() -> None:
    """Reading the bases in the order they are written would give 'Y'."""
    app = Diamond().build()
    assert app.motor.axis == "Z"
    assert app.ctrl.gain == 9.0


def test_the_constructor_layers_over_the_class() -> None:
    """Naming one key changes that key, rather than replacing the whole."""
    app = Layered({"presenters": {"ctrl": {"gain": 4.0}}}).build()
    assert app.ctrl.gain == 4.0
    assert app.virtual_container.name == "layered"
    assert app.motor.axis == "Z"


def test_a_file_and_a_mapping_are_both_sources(tmp_path: Path) -> None:
    """A string is a path, not the sequence of characters it also is."""
    shared = tmp_path / "shared.yaml"
    shared.write_text("name: from-file\npresenters:\n  ctrl:\n    gain: 3.0\n")

    class Mixed(AppContainer):
        config: ClassVar[list[Any]] = [str(shared), {"name": "from-mapping"}]

        motor: AsDevice[Stage]
        ctrl: AsPresenter[Ctrl]

    app = Mixed().build()
    assert app.virtual_container.name == "from-mapping"
    assert app.ctrl.gain == 3.0


def test_sources_must_agree_on_what_the_session_is() -> None:
    """A later source says more about a session, never that it is another."""

    class Contradiction(AppContainer):
        config: ClassVar[list[Any]] = [{"frontend": "pyqt"}, {"frontend": "pyside"}]

    with pytest.raises(ValueError, match="frontend"):
        Contradiction().build()


def test_a_later_source_may_rename_the_session() -> None:
    """The name is content rather than identity, so an overlay may set it."""

    class Renamed(AppContainer):
        config: ClassVar[list[Any]] = [{"name": "first"}, {"name": "second"}]

    app = Renamed().build()
    assert app.virtual_container.name == "second"
