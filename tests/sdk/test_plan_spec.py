from __future__ import annotations

from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from inspect import Parameter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

import numpy as np
import pytest
from bluesky.utils import MsgGenerator
from magicgui import widgets as mgw
from ophyd_async.core import (
    Device,
    SignalR,
    SignalRW,
    StandardReadable,
    soft_signal_r_and_setter,
    soft_signal_rw,
)

from redsun.engine.actions import Action, continous
from redsun.presenter.plan_spec import (
    ParamDescription,
    ParamKind,
    PlanSpec,
    UnresolvableAnnotationError,
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)
from redsun.presenter.utils import isdevice, isdevicesequence, isdeviceset, issequence
from redsun.view.qt._device_sequence_edit import DeviceSequenceEdit
from redsun.view.qt._widget_factory import create_param_widget

if TYPE_CHECKING:
    from collections.abc import Callable

    # deliberately never imported at runtime: a plan annotated with it
    # reproduces a plugin author hiding an import behind TYPE_CHECKING
    from decimal import Decimal

    from qtpy.QtWidgets import QApplication


@runtime_checkable
class _MotorProtocol(Protocol):
    """Motor protocol: requires child axis sub-devices."""

    x: Device
    y: Device


@runtime_checkable
class _DetectorProtocol(Protocol):
    """Detector protocol: ROI is settable; sensor shape is fixed."""

    roi: SignalRW[np.ndarray]
    sensor_shape: SignalR[np.ndarray]


class _MockAxis(Device):
    """Minimal single-axis device for motor protocol tests."""

    position: SignalRW[float]

    def __init__(self, name: str = "") -> None:
        self.position = soft_signal_rw(float, initial_value=0.0, units="mm")
        super().__init__(name=name)


class _MockDetector(StandardReadable):
    """Mock detector satisfying [`_DetectorProtocol`][tests.sdk.test_plan_spec._DetectorProtocol]."""

    roi: SignalRW[np.ndarray]
    sensor_shape: SignalR[np.ndarray]

    def __init__(self, name: str) -> None:
        with self.add_children_as_readables():
            self.roi = soft_signal_rw(
                np.ndarray, initial_value=np.array([0, 0, 512, 512], dtype=np.int32)
            )
            self.sensor_shape, _ = soft_signal_r_and_setter(
                np.ndarray, initial_value=np.array([512, 512], dtype=np.int32)
            )
        super().__init__(name=name)


class MockMotorDevice(StandardReadable):
    """Mock motor satisfying [`_MotorProtocol`][tests.sdk.test_plan_spec._MotorProtocol]."""

    x: _MockAxis
    y: _MockAxis

    def __init__(self, name: str, /) -> None:
        self.x = _MockAxis()
        self.y = _MockAxis()
        super().__init__(name=name)


@pytest.fixture
def mock_motor(name: str = "stage") -> MockMotorDevice:
    """Single mock motor device."""
    return MockMotorDevice(name)


@pytest.fixture
def one_detector() -> dict[str, _MockDetector]:
    return {"cam": _MockDetector("cam")}


@pytest.fixture
def one_motor(mock_motor: MockMotorDevice) -> dict[str, MockMotorDevice]:
    return {"stage": mock_motor}


def _param(
    name: str,
    annotation: object = int,
    kind: ParamKind = ParamKind.POSITIONAL_OR_KEYWORD,
    default: object = Parameter.empty,
    **fields: Any,
) -> ParamDescription:
    return ParamDescription(
        name=name, kind=kind, annotation=annotation, default=default, **fields
    )


def _make_spec(*params: ParamDescription) -> PlanSpec:
    return PlanSpec(name="plan", docs="", parameters=list(params))


@pytest.mark.parametrize(
    ("predicate", "annotation", "expected"),
    [
        (isdevice, _DetectorProtocol, True),
        (isdevice, _MotorProtocol, True),
        (isdevice, int, False),
        (isdevice, str, False),
        (isdevice, 42, False),
        (isdevicesequence, Sequence[_DetectorProtocol], True),
        (isdevicesequence, Sequence[_MotorProtocol], True),
        (isdevicesequence, Sequence[int], False),
        (isdevicesequence, _DetectorProtocol, False),
        (isdeviceset, set[_DetectorProtocol], True),
        (isdeviceset, AbstractSet[_DetectorProtocol], True),
        (isdeviceset, frozenset[_DetectorProtocol], True),
        (isdeviceset, set[int], False),
        (isdeviceset, _DetectorProtocol, False),
        (isdeviceset, Sequence[_DetectorProtocol], False),
        (issequence, Sequence[int], True),
        (issequence, list[float], True),
        (issequence, str, False),
        (issequence, int, False),
    ],
)
def test_the_annotation_predicates(
    predicate: Callable[[object], bool], annotation: object, expected: bool
) -> None:
    assert predicate(annotation) is expected


class TestCreatePlanSpec:
    """Tests for ``create_plan_spec`` across the supported annotation shapes."""

    def test_int_param(self) -> None:
        def plan(x: int) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        p = spec.parameters[0]
        assert p.name == "x"
        assert p.annotation is int
        assert p.choices is None
        assert p.device_proto is None

    def test_float_param_with_default(self) -> None:
        def plan(step: float = 1.0) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        p = spec.parameters[0]
        assert p.has_default
        assert p.default == pytest.approx(1.0)

    def test_literal_produces_string_choices(self) -> None:
        def plan(egu: Literal["um", "mm", "nm"] = "um") -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        p = spec.parameters[0]
        assert p.choices == ["um", "mm", "nm"]
        assert p.device_proto is None
        assert not p.multiselect

    @pytest.mark.parametrize("default", ["", (), []], ids=["str", "tuple", "list"])
    def test_an_empty_sequence_default_is_not_an_action_list(
        self, default: Any
    ) -> None:
        def plan(label: Sequence[str] = default) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})

        assert spec.parameters[0].actions is None
        assert spec.parameters[0].default == default

    def test_an_already_evaluated_annotation_is_taken_as_it_is(self) -> None:
        """A module without the annotations future import evaluates them itself."""

        def plan(n=1):  # type: ignore[no-untyped-def]
            yield from ()

        plan.__annotations__ = {"n": int, "return": MsgGenerator[None]}

        spec = create_plan_spec(plan, {})

        assert spec.parameters[0].annotation is int

    def test_literal_values_are_kept_as_they_are(self) -> None:
        def plan(n: Literal[1, 2, 3] = 1) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        assert spec.parameters[0].choices == [1, 2, 3]

    def test_single_device_param_populates_choices(
        self, one_motor: dict[str, MockMotorDevice]
    ) -> None:
        def plan(motor: _MotorProtocol) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, one_motor)
        p = spec.parameters[0]
        assert p.choices == ["stage"]
        assert not p.multiselect
        assert p.device_proto is _MotorProtocol

    def test_single_device_no_registry_match_raises(self) -> None:
        """A required PDevice parameter with no matching devices is unresolvable.

        The plan cannot be driven from the UI without at least one matching
        device in the registry, so ``create_plan_spec`` raises rather than
        producing a param with ``choices=None`` that would silently break.
        """

        def plan(motor: _MotorProtocol) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})
        assert exc_info.value.param_name == "motor"

    def test_single_device_no_registry_match_ok_with_default(self) -> None:
        """A PDevice param with a default is fine even with an empty registry."""

        def plan(motor: _MotorProtocol = None) -> MsgGenerator[None]:  # type: ignore[assignment]
            yield from ()

        spec = create_plan_spec(plan, {})
        assert spec.parameters[0].choices is None  # no match, but has default

    def test_sequence_device_param_is_multiselect(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        def plan(dets: Sequence[_DetectorProtocol]) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.choices == ["cam"]
        assert p.multiselect
        assert p.device_proto is _DetectorProtocol

    def test_set_device_param_is_multiselect(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        def plan(dets: set[_DetectorProtocol]) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.choices == ["cam"]
        assert p.multiselect
        assert p.device_proto is _DetectorProtocol

    def test_var_positional_device_is_multiselect(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        def plan(*dets: _DetectorProtocol) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.kind is ParamKind.VAR_POSITIONAL
        assert p.choices == ["cam"]
        assert p.multiselect

    def test_action_param_has_no_choices_and_stores_meta(self) -> None:
        @dataclass
        class Snap(Action):
            name: str = "snap"

        def plan(frames: int = 1, /, snap: Action = Snap()) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        action_p = next(p for p in spec.parameters if p.name == "snap")
        assert action_p.actions is not None
        assert isinstance(action_p.actions, Action)
        assert action_p.choices is None

    def test_action_sequence_param(self) -> None:
        @dataclass
        class A(Action):
            name: str = "a"

        @dataclass
        class B(Action):
            name: str = "b"

        def plan(
            frames: int = 1,
            /,
            actions: Action = [A(), B()],  # type: ignore[assignment]
        ) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        p = next(q for q in spec.parameters if q.name == "actions")
        assert isinstance(p.actions, list)
        assert len(p.actions) == 2

    def test_togglable_flag(self) -> None:
        @continous(togglable=True, pausable=True)
        def plan() -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        assert spec.togglable is True
        assert spec.pausable is True

    def test_non_togglable_plan(self) -> None:
        def plan(x: int) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        assert spec.togglable is False
        assert spec.pausable is False

    def test_self_is_stripped_from_method_signature(self) -> None:
        class Presenter:
            def plan(self, x: int) -> MsgGenerator[None]:
                yield from ()

        spec = create_plan_spec(Presenter.plan, {})
        assert all(p.name != "self" for p in spec.parameters)
        assert spec.parameters[0].name == "x"

    def test_non_generator_raises_type_error(self) -> None:
        def not_a_plan(x: int) -> int:
            return x

        with pytest.raises(TypeError, match="generator function"):
            create_plan_spec(not_a_plan, {})  # type: ignore[arg-type]

    def test_missing_return_annotation_raises(self) -> None:
        def plan(x: int):  # type: ignore[no-untyped-def]
            yield from ()

        with pytest.raises(TypeError, match="return type annotation"):
            create_plan_spec(plan, {})

    def test_wrong_return_type_raises(self) -> None:
        def plan(x: int) -> list[int]:  # type: ignore[misc]
            yield x

        with pytest.raises(TypeError, match="MsgGenerator"):
            create_plan_spec(plan, {})  # type: ignore[arg-type]


class TestUnresolvableAnnotation:
    """Tests for the unresolvable-annotation guard."""

    class _Exotic:
        """A type magicgui has no idea how to handle."""

    def test_required_exotic_param_raises(self) -> None:
        def bad_plan(thing: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(bad_plan, {})

        err = exc_info.value
        assert err.param_name == "thing"
        assert err.plan_name == "bad_plan"
        assert err.annotation is TestUnresolvableAnnotation._Exotic

    def test_optional_exotic_param_does_not_raise(self) -> None:
        """A param with a default value is never required - plan should succeed."""
        default_val = TestUnresolvableAnnotation._Exotic()

        def ok_plan(
            thing: TestUnresolvableAnnotation._Exotic = default_val,
        ) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(ok_plan, {})
        assert spec.parameters[0].name == "thing"

    def test_var_keyword_exotic_does_not_raise(self) -> None:
        """**kwargs are never turned into widgets; no probe needed."""

        def ok_plan(**kw: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(ok_plan, {})
        assert spec.parameters[0].kind is ParamKind.VAR_KEYWORD

    def test_error_message_contains_plan_and_param_name(self) -> None:
        def broken(widget: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError, match="broken") as exc_info:
            create_plan_spec(broken, {})

        assert "widget" in str(exc_info.value)
        assert "broken" in str(exc_info.value)


class TestTypeCheckingOnlyAnnotation:
    """A name available only to a type checker is reported, not raised as NameError."""

    def test_required_param_raises_unresolvable(self) -> None:
        def plan(amount: Decimal) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})

        err = exc_info.value
        assert err.plan_name == "plan"
        assert err.param_name == "amount"
        assert err.annotation == "Decimal"

    def test_unresolvable_return_raises_unresolvable(self) -> None:
        def plan(count: int) -> Decimal:  # type: ignore[misc]
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})  # type: ignore[arg-type]

        assert exc_info.value.param_name == "return"

    def test_resolvable_siblings_do_not_mask_the_bad_one(self) -> None:
        """The failure names the offending parameter, not the first one."""

        def plan(count: int, path: Path, amount: Decimal) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})

        assert exc_info.value.param_name == "amount"

    def test_optional_unresolvable_param_still_raises(self) -> None:
        """Strict by design: a default does not make an unreadable name acceptable."""

        def plan(amount: Decimal | None = None) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError):
            create_plan_spec(plan, {})


class TestCollectArguments:
    """Tests for ``collect_arguments``."""

    def test_positional_only(self) -> None:
        spec = _make_spec(_param("x", kind=ParamKind.POSITIONAL_ONLY))
        args, kwargs = collect_arguments(spec, {"x": 42})
        assert args == (42,)
        assert kwargs == {}

    def test_positional_or_keyword(self) -> None:
        spec = _make_spec(_param("x", kind=ParamKind.POSITIONAL_OR_KEYWORD))
        args, kwargs = collect_arguments(spec, {"x": 7})
        assert args == (7,)
        assert kwargs == {}

    def test_keyword_only(self) -> None:
        spec = _make_spec(_param("n", kind=ParamKind.KEYWORD_ONLY))
        args, kwargs = collect_arguments(spec, {"n": 3})
        assert args == ()
        assert kwargs == {"n": 3}

    def test_var_positional_sequence_expanded(self) -> None:
        spec = _make_spec(_param("vals", kind=ParamKind.VAR_POSITIONAL))
        args, _kwargs = collect_arguments(spec, {"vals": [1, 2, 3]})
        assert args == (1, 2, 3)

    def test_var_positional_single_value_wrapped(self) -> None:
        spec = _make_spec(_param("vals", kind=ParamKind.VAR_POSITIONAL))
        args, _kwargs = collect_arguments(spec, {"vals": 99})
        assert args == (99,)

    def test_var_keyword_mapping_merged(self) -> None:
        spec = _make_spec(_param("kw", kind=ParamKind.VAR_KEYWORD))
        _args, kwargs = collect_arguments(spec, {"kw": {"a": 1, "b": 2}})
        assert kwargs == {"a": 1, "b": 2}

    def test_var_keyword_non_mapping_raises(self) -> None:
        spec = _make_spec(_param("kw", kind=ParamKind.VAR_KEYWORD))
        with pytest.raises(TypeError, match="Mapping"):
            collect_arguments(spec, {"kw": "not_a_mapping"})

    def test_missing_param_skipped(self) -> None:
        spec = _make_spec(
            _param("x", kind=ParamKind.POSITIONAL_OR_KEYWORD),
            _param("y", kind=ParamKind.POSITIONAL_OR_KEYWORD),
        )
        args, _kwargs = collect_arguments(spec, {"x": 1})
        assert args == (1,)

    def test_ordering_preserved(self) -> None:
        spec = _make_spec(
            _param("a", kind=ParamKind.POSITIONAL_OR_KEYWORD),
            _param("b", kind=ParamKind.POSITIONAL_OR_KEYWORD),
            _param("c", kind=ParamKind.POSITIONAL_OR_KEYWORD),
        )
        args, _ = collect_arguments(spec, {"a": 1, "b": 2, "c": 3})
        assert args == (1, 2, 3)


class TestResolveArguments:
    """Tests for ``resolve_arguments``."""

    def test_non_device_param_passed_through(self) -> None:
        spec = _make_spec(
            ParamDescription(
                name="frames",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=int,
                default=1,
            )
        )
        resolved = resolve_arguments(spec, {"frames": 5}, {})
        assert resolved["frames"] == 5

    def test_action_injected_when_absent(self) -> None:
        @dataclass
        class MyAction(Action):
            name: str = "go"

        action_instance = MyAction()
        spec = _make_spec(
            ParamDescription(
                name="go",
                kind=ParamKind.POSITIONAL_ONLY,
                annotation=Action,
                default=action_instance,
                actions=action_instance,
            )
        )
        resolved = resolve_arguments(spec, {}, {})
        assert resolved["go"] is action_instance

    def test_action_not_overwritten_when_present(self) -> None:
        @dataclass
        class MyAction(Action):
            name: str = "go"

        a1 = MyAction()
        a2 = MyAction()
        spec = _make_spec(
            ParamDescription(
                name="go",
                kind=ParamKind.POSITIONAL_ONLY,
                annotation=Action,
                default=a1,
                actions=a1,
            )
        )
        resolved = resolve_arguments(spec, {"go": a2}, {})
        assert resolved["go"] is a2

    def test_single_device_label_resolved(
        self, one_motor: dict[str, MockMotorDevice]
    ) -> None:
        spec = _make_spec(
            ParamDescription(
                name="motor",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=_MotorProtocol,
                default=Parameter.empty,
                choices=["stage"],
                device_proto=_MotorProtocol,
            )
        )
        resolved = resolve_arguments(spec, {"motor": "stage"}, one_motor)
        assert resolved["motor"] is one_motor["stage"]

    def test_device_sequence_labels_resolved(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        spec = _make_spec(
            ParamDescription(
                name="dets",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=Sequence[_DetectorProtocol],
                default=Parameter.empty,
                choices=["cam"],
                multiselect=True,
                device_proto=_DetectorProtocol,
            )
        )
        resolved = resolve_arguments(spec, {"dets": ["cam"]}, one_detector)
        assert resolved["dets"] == [one_detector["cam"]]

    def test_device_set_labels_resolved(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        spec = _make_spec(
            ParamDescription(
                name="dets",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=set[_DetectorProtocol],
                default=Parameter.empty,
                choices=["cam"],
                multiselect=True,
                device_proto=_DetectorProtocol,
            )
        )
        resolved = resolve_arguments(spec, {"dets": ["cam"]}, one_detector)
        assert resolved["dets"] == {one_detector["cam"]}

    def test_unknown_label_resolves_to_none_for_single(
        self, one_motor: dict[str, MockMotorDevice]
    ) -> None:
        spec = _make_spec(
            ParamDescription(
                name="motor",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=_MotorProtocol,
                default=Parameter.empty,
                choices=["stage"],
                device_proto=_MotorProtocol,
            )
        )
        resolved = resolve_arguments(spec, {"motor": "nonexistent"}, one_motor)
        assert resolved["motor"] is None


@pytest.mark.qt
class TestCreateParamWidget:
    """Tests for ``create_param_widget``, which builds Qt widgets."""

    @pytest.fixture(autouse=True)
    def _application(self, qapp: QApplication) -> None:
        """Hold the session's application, so magicgui makes none of its own."""

    def test_int_creates_spinbox(self) -> None:
        w = create_param_widget(_param("n", int))
        assert isinstance(w, mgw.SpinBox)

    def test_float_creates_float_spinbox(self) -> None:
        w = create_param_widget(_param("x", float))
        assert isinstance(w, mgw.FloatSpinBox)

    def test_bool_creates_checkbox(self) -> None:
        w = create_param_widget(_param("flag", bool, default=False))
        assert isinstance(w, mgw.CheckBox)

    def test_literal_creates_combobox(self) -> None:
        p = _param("egu", Literal["um", "mm"], choices=["um", "mm"])
        w = create_param_widget(p)
        assert isinstance(w, mgw.ComboBox)

    def test_single_device_creates_combobox(self) -> None:
        p = _param(
            "motor",
            _MotorProtocol,
            choices=["stage"],
            device_proto=_MotorProtocol,
        )
        w = create_param_widget(p)
        assert isinstance(w, mgw.ComboBox)

    def test_multiselect_device_creates_device_sequence_edit(self) -> None:
        p = _param(
            "dets",
            Sequence[_DetectorProtocol],
            choices=["cam"],
            multiselect=True,
            device_proto=_DetectorProtocol,
        )
        w = create_param_widget(p)
        assert isinstance(w, DeviceSequenceEdit)

    def test_path_creates_file_edit(self) -> None:
        w = create_param_widget(_param("output", Path))
        assert isinstance(w, mgw.FileEdit)

    def test_sequence_int_creates_list_edit(self) -> None:
        w = create_param_widget(_param("vals", Sequence[int]))
        assert isinstance(w, mgw.ListEdit)

    def test_hidden_param_creates_line_edit_placeholder(self) -> None:
        p = _param("secret", int, hidden=True)
        w = create_param_widget(p)
        assert isinstance(w, mgw.LineEdit)

    def test_action_param_creates_line_edit_placeholder(self) -> None:
        @dataclass
        class Snap(Action):
            name: str = "snap"

        snap = Snap()
        p = _param("snap", Action, actions=snap)
        w = create_param_widget(p)
        assert isinstance(w, mgw.LineEdit)
