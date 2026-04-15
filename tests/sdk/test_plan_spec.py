from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from inspect import Parameter
from pathlib import Path
from typing import Any, FrozenSet, Literal, Protocol, Set, runtime_checkable

import numpy as np
import pytest
from bluesky.utils import MsgGenerator
from magicgui import widgets as mgw

from redsun.device import (
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
    _dispatch_annotation,
    _FieldsFromAnnotation,
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)
from redsun.presenter.utils import isdevice, isdevicesequence, isdeviceset, issequence
from redsun.view.qt._device_sequence_edit import DeviceSequenceEdit
from redsun.view.qt._widget_factory import create_param_widget


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

    roi: SignalRW[tuple[int, int, int, int]]
    sensor_shape: SignalR[tuple[int, int]]

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


class TestTypePredicates:
    """Unit tests for the annotation-classification helpers in ``utils``."""

    def test_isdevice_true_for_detector_protocol(self) -> None:
        assert isdevice(_DetectorProtocol)

    def test_isdevice_true_for_motor_protocol(self) -> None:
        assert isdevice(_MotorProtocol)

    def test_isdevice_false_for_primitive(self) -> None:
        assert not isdevice(int)
        assert not isdevice(str)
        assert not isdevice(float)

    def test_isdevice_false_for_instance(self) -> None:
        assert not isdevice(42)
        assert not isdevice("hello")

    def test_isdevicesequence_true(self) -> None:
        assert isdevicesequence(Sequence[_DetectorProtocol])
        assert isdevicesequence(Sequence[_MotorProtocol])

    def test_isdevicesequence_false_for_primitive_sequence(self) -> None:
        assert not isdevicesequence(Sequence[int])
        assert not isdevicesequence(Sequence[str])

    def test_isdevicesequence_false_for_bare_type(self) -> None:
        assert not isdevicesequence(_DetectorProtocol)

    def test_isdeviceset_true(self) -> None:
        assert isdeviceset(Set[_DetectorProtocol])
        assert isdeviceset(Set[_MotorProtocol])
        assert isdeviceset(AbstractSet[_DetectorProtocol])
        assert isdeviceset(FrozenSet[_DetectorProtocol])

    def test_isdeviceset_false_for_primitive_set(self) -> None:
        assert not isdeviceset(Set[int])
        assert not isdeviceset(FrozenSet[str])

    def test_isdeviceset_false_for_bare_type(self) -> None:
        assert not isdeviceset(_DetectorProtocol)

    def test_isdeviceset_false_for_sequence(self) -> None:
        assert not isdeviceset(Sequence[_DetectorProtocol])

    def test_issequence_true_for_generic_alias(self) -> None:
        assert issequence(Sequence[int])
        assert issequence(list[float])

    def test_issequence_false_for_str(self) -> None:
        assert not issequence(str)

    def test_issequence_false_for_bare_class(self) -> None:
        assert not issequence(int)


class TestCreatePlanSpec:
    """Tests for ``create_plan_spec`` across the supported annotation shapes."""

    def test_int_param(self) -> None:
        def plan(x: int) -> MsgGenerator[None]:
            yield

        spec = create_plan_spec(plan, {})
        p = spec.parameters[0]
        assert p.name == "x"
        assert p.annotation is int
        assert p.choices is None
        assert p.device_proto is None

    def test_float_param_with_default(self) -> None:
        def plan(step: float = 1.0) -> MsgGenerator[None]:
            yield

        spec = create_plan_spec(plan, {})
        p = spec.parameters[0]
        assert p.has_default
        assert p.default == pytest.approx(1.0)

    def test_literal_produces_string_choices(self) -> None:
        def plan(egu: Literal["um", "mm", "nm"] = "um") -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(plan, {})
        p = spec.parameters[0]
        assert p.choices == ["um", "mm", "nm"]
        assert p.device_proto is None
        assert not p.multiselect

    def test_literal_with_int_values_stringified(self) -> None:
        def plan(n: Literal[1, 2, 3] = 1) -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(plan, {})
        assert spec.parameters[0].choices == ["1", "2", "3"]

    def test_single_device_param_populates_choices(
        self, one_motor: dict[str, MockMotorDevice]
    ) -> None:
        def plan(motor: _MotorProtocol) -> MsgGenerator[None]:
            yield

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
            yield  # type: ignore

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})
        assert exc_info.value.param_name == "motor"

    def test_single_device_no_registry_match_ok_with_default(self) -> None:
        """A PDevice param with a default is fine even with an empty registry."""

        def plan(motor: _MotorProtocol = None) -> MsgGenerator[None]:  # type: ignore[assignment]
            yield  # type: ignore

        spec = create_plan_spec(plan, {})
        assert spec.parameters[0].choices is None  # no match, but has default

    # ---- Sequence[PDevice] ------------------------------------------------

    def test_sequence_device_param_is_multiselect(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        def plan(dets: Sequence[_DetectorProtocol]) -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.choices == ["cam"]
        assert p.multiselect
        assert p.device_proto is _DetectorProtocol

    def test_set_device_param_is_multiselect(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        def plan(dets: Set[_DetectorProtocol]) -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.choices == ["cam"]
        assert p.multiselect
        assert p.device_proto is _DetectorProtocol

    # ---- VAR_POSITIONAL device (*args) ------------------------------------

    def test_var_positional_device_is_multiselect(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        def plan(*dets: _DetectorProtocol) -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.kind is ParamKind.VAR_POSITIONAL
        assert p.choices == ["cam"]
        assert p.multiselect

    # ---- Action parameters ------------------------------------------------

    def test_action_param_has_no_choices_and_stores_meta(self) -> None:
        @dataclass
        class Snap(Action):
            name: str = "snap"

        def plan(frames: int = 1, /, snap: Action = Snap()) -> MsgGenerator[None]:
            yield  # type: ignore

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
            yield  # type: ignore

        spec = create_plan_spec(plan, {})
        p = next(q for q in spec.parameters if q.name == "actions")
        assert isinstance(p.actions, list)
        assert len(p.actions) == 2

    # ---- toggleable / pausable flags --------------------------------------

    def test_togglable_flag(self) -> None:
        @continous(togglable=True, pausable=True)
        def plan() -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(plan, {})
        assert spec.togglable is True
        assert spec.pausable is True

    def test_non_togglable_plan(self) -> None:
        def plan(x: int) -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(plan, {})
        assert spec.togglable is False
        assert spec.pausable is False

    # ---- self/cls stripping -----------------------------------------------

    def test_self_is_stripped_from_method_signature(self) -> None:
        class Presenter:
            def plan(self, x: int) -> MsgGenerator[None]:
                yield  # type: ignore

        spec = create_plan_spec(Presenter.plan, {})
        assert all(p.name != "self" for p in spec.parameters)
        assert spec.parameters[0].name == "x"

    # ---- error cases -------------------------------------------------------

    def test_non_generator_raises_type_error(self) -> None:
        def not_a_plan(x: int) -> int:
            return x

        with pytest.raises(TypeError, match="generator function"):
            create_plan_spec(not_a_plan, {})  # type: ignore[arg-type]

    def test_missing_return_annotation_raises(self) -> None:
        def plan(x: int):  # type: ignore[no-untyped-def]
            yield

        with pytest.raises(TypeError, match="return type annotation"):
            create_plan_spec(plan, {})

    def test_wrong_return_type_raises(self) -> None:
        def plan(x: int) -> list[int]:  # type: ignore[misc]
            yield x

        with pytest.raises(TypeError, match="MsgGenerator"):
            create_plan_spec(plan, {})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# UnresolvableAnnotationError
# ---------------------------------------------------------------------------


class TestUnresolvableAnnotation:
    """Tests for the Option-B unresolvable-annotation guard."""

    class _Exotic:
        """A type magicgui has no idea how to handle."""

    def test_required_exotic_param_raises(self) -> None:
        def bad_plan(thing: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield  # type: ignore

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(bad_plan, {})

        err = exc_info.value
        assert err.param_name == "thing"
        assert err.plan_name == "bad_plan"
        assert err.annotation is TestUnresolvableAnnotation._Exotic

    def test_optional_exotic_param_does_not_raise(self) -> None:
        """A param with a default value is never required — plan should succeed."""
        default_val = TestUnresolvableAnnotation._Exotic()

        def ok_plan(
            thing: TestUnresolvableAnnotation._Exotic = default_val,
        ) -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(ok_plan, {})
        assert spec.parameters[0].name == "thing"

    def test_var_keyword_exotic_does_not_raise(self) -> None:
        """**kwargs are never turned into widgets; no probe needed."""

        def ok_plan(**kw: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield  # type: ignore

        spec = create_plan_spec(ok_plan, {})
        assert spec.parameters[0].kind is ParamKind.VAR_KEYWORD

    def test_error_message_contains_plan_and_param_name(self) -> None:
        def broken(widget: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield  # type: ignore

        with pytest.raises(UnresolvableAnnotationError, match="broken") as exc_info:
            create_plan_spec(broken, {})

        assert "widget" in str(exc_info.value)
        assert "broken" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _dispatch_annotation: table entry selection
# ---------------------------------------------------------------------------


class TestDispatchAnnotation:
    """Direct unit tests for ``_dispatch_annotation``."""

    def test_literal_dispatched(self) -> None:
        fields = _dispatch_annotation(Literal["a", "b"], ParamKind.KEYWORD_ONLY, {})
        assert fields.choices == ["a", "b"]
        assert fields.device_proto is None

    def test_device_sequence_dispatched(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        fields = _dispatch_annotation(
            Sequence[_DetectorProtocol],
            ParamKind.POSITIONAL_OR_KEYWORD,
            one_detector,
        )
        assert fields.choices == ["cam"]
        assert fields.multiselect is True
        assert fields.device_proto is _DetectorProtocol

    def test_device_set_dispatched(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        fields = _dispatch_annotation(
            Set[_DetectorProtocol],
            ParamKind.POSITIONAL_OR_KEYWORD,
            one_detector,
        )
        assert fields.choices == ["cam"]
        assert fields.multiselect is True
        assert fields.device_proto is _DetectorProtocol

    def test_single_device_dispatched(
        self, one_motor: dict[str, MockMotorDevice]
    ) -> None:
        fields = _dispatch_annotation(
            _MotorProtocol, ParamKind.POSITIONAL_OR_KEYWORD, one_motor
        )
        assert fields.choices == ["stage"]
        assert fields.multiselect is False

    def test_var_positional_device_dispatched(
        self, one_detector: dict[str, _MockDetector]
    ) -> None:
        fields = _dispatch_annotation(
            _DetectorProtocol, ParamKind.VAR_POSITIONAL, one_detector
        )
        assert fields.multiselect is True
        assert fields.choices == ["cam"]

    def test_primitive_falls_through_to_empty(self) -> None:
        fields = _dispatch_annotation(int, ParamKind.POSITIONAL_OR_KEYWORD, {})
        assert fields == _FieldsFromAnnotation()

    def test_empty_registry_gives_no_choices_for_device(self) -> None:
        fields = _dispatch_annotation(
            _MotorProtocol, ParamKind.POSITIONAL_OR_KEYWORD, {}
        )
        assert fields.choices is None


# ---------------------------------------------------------------------------
# collect_arguments
# ---------------------------------------------------------------------------


class TestCollectArguments:
    """Tests for ``collect_arguments``."""

    def _make_spec(self, *params: ParamDescription) -> PlanSpec:
        return PlanSpec(name="plan", docs="", parameters=list(params))

    def _param(
        self,
        name: str,
        kind: ParamKind,
        annotation: object = int,
        default: object = Parameter.empty,
    ) -> ParamDescription:
        return ParamDescription(
            name=name,
            kind=kind,
            annotation=annotation,
            default=default,
        )

    def test_positional_only(self) -> None:
        spec = self._make_spec(self._param("x", ParamKind.POSITIONAL_ONLY))
        args, kwargs = collect_arguments(spec, {"x": 42})
        assert args == (42,)
        assert kwargs == {}

    def test_positional_or_keyword(self) -> None:
        spec = self._make_spec(self._param("x", ParamKind.POSITIONAL_OR_KEYWORD))
        args, kwargs = collect_arguments(spec, {"x": 7})
        assert args == (7,)
        assert kwargs == {}

    def test_keyword_only(self) -> None:
        spec = self._make_spec(self._param("n", ParamKind.KEYWORD_ONLY))
        args, kwargs = collect_arguments(spec, {"n": 3})
        assert args == ()
        assert kwargs == {"n": 3}

    def test_var_positional_sequence_expanded(self) -> None:
        spec = self._make_spec(self._param("vals", ParamKind.VAR_POSITIONAL))
        args, kwargs = collect_arguments(spec, {"vals": [1, 2, 3]})
        assert args == (1, 2, 3)

    def test_var_positional_single_value_wrapped(self) -> None:
        spec = self._make_spec(self._param("vals", ParamKind.VAR_POSITIONAL))
        args, kwargs = collect_arguments(spec, {"vals": 99})
        assert args == (99,)

    def test_var_keyword_mapping_merged(self) -> None:
        spec = self._make_spec(self._param("kw", ParamKind.VAR_KEYWORD))
        args, kwargs = collect_arguments(spec, {"kw": {"a": 1, "b": 2}})
        assert kwargs == {"a": 1, "b": 2}

    def test_var_keyword_non_mapping_raises(self) -> None:
        spec = self._make_spec(self._param("kw", ParamKind.VAR_KEYWORD))
        with pytest.raises(TypeError, match="Mapping"):
            collect_arguments(spec, {"kw": "not_a_mapping"})

    def test_missing_param_skipped(self) -> None:
        spec = self._make_spec(
            self._param("x", ParamKind.POSITIONAL_OR_KEYWORD),
            self._param("y", ParamKind.POSITIONAL_OR_KEYWORD),
        )
        args, kwargs = collect_arguments(spec, {"x": 1})
        assert args == (1,)

    def test_ordering_preserved(self) -> None:
        spec = self._make_spec(
            self._param("a", ParamKind.POSITIONAL_OR_KEYWORD),
            self._param("b", ParamKind.POSITIONAL_OR_KEYWORD),
            self._param("c", ParamKind.POSITIONAL_OR_KEYWORD),
        )
        args, _ = collect_arguments(spec, {"a": 1, "b": 2, "c": 3})
        assert args == (1, 2, 3)


# ---------------------------------------------------------------------------
# resolve_arguments
# ---------------------------------------------------------------------------


class TestResolveArguments:
    """Tests for ``resolve_arguments``."""

    def _make_spec(self, *params: ParamDescription) -> PlanSpec:
        return PlanSpec(name="plan", docs="", parameters=list(params))

    def test_non_device_param_passed_through(self) -> None:
        spec = self._make_spec(
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
        spec = self._make_spec(
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
        spec = self._make_spec(
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
        spec = self._make_spec(
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
        spec = self._make_spec(
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
        spec = self._make_spec(
            ParamDescription(
                name="dets",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=Set[_DetectorProtocol],
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
        spec = self._make_spec(
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


# ---------------------------------------------------------------------------
# create_param_widget: factory registry
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "linux" and not os.environ.get("DISPLAY"),
    reason="requires a display (Qt) on Linux",
)
class TestCreateParamWidget:
    """Tests for ``create_param_widget`` — requires a Qt platform."""

    def _param(
        self,
        name: str,
        annotation: object,
        kind: ParamKind = ParamKind.POSITIONAL_OR_KEYWORD,
        default: object = Parameter.empty,
        choices: list[str] | None = None,
        multiselect: bool = False,
        device_proto: type[Any] | None = None,
        actions: Sequence[Action] | Action | None = None,
        hidden: bool = False,
    ) -> ParamDescription:
        return ParamDescription(
            name=name,
            kind=kind,
            annotation=annotation,
            default=default,
            choices=choices,
            multiselect=multiselect,
            device_proto=device_proto,
            actions=actions,
            hidden=hidden,
        )

    def test_int_creates_spinbox(self) -> None:
        w = create_param_widget(self._param("n", int))
        assert isinstance(w, mgw.SpinBox)

    def test_float_creates_float_spinbox(self) -> None:
        w = create_param_widget(self._param("x", float))
        assert isinstance(w, mgw.FloatSpinBox)

    def test_bool_creates_checkbox(self) -> None:
        w = create_param_widget(self._param("flag", bool, default=False))
        assert isinstance(w, mgw.CheckBox)

    def test_literal_creates_combobox(self) -> None:
        p = self._param("egu", Literal["um", "mm"], choices=["um", "mm"])
        w = create_param_widget(p)
        assert isinstance(w, mgw.ComboBox)

    def test_single_device_creates_combobox(self) -> None:
        p = self._param(
            "motor",
            _MotorProtocol,
            choices=["stage"],
            device_proto=_MotorProtocol,
        )
        w = create_param_widget(p)
        assert isinstance(w, mgw.ComboBox)

    def test_multiselect_device_creates_device_sequence_edit(self) -> None:
        p = self._param(
            "dets",
            Sequence[_DetectorProtocol],
            choices=["cam"],
            multiselect=True,
            device_proto=_DetectorProtocol,
        )
        w = create_param_widget(p)
        assert isinstance(w, DeviceSequenceEdit)

    def test_path_creates_file_edit(self) -> None:
        w = create_param_widget(self._param("output", Path))
        assert isinstance(w, mgw.FileEdit)

    def test_sequence_int_creates_list_edit(self) -> None:
        w = create_param_widget(self._param("vals", Sequence[int]))
        assert isinstance(w, mgw.ListEdit)

    def test_hidden_param_creates_line_edit_placeholder(self) -> None:
        p = self._param("secret", int, hidden=True)
        w = create_param_widget(p)
        assert isinstance(w, mgw.LineEdit)

    def test_action_param_creates_line_edit_placeholder(self) -> None:
        @dataclass
        class Snap(Action):
            name: str = "snap"

        snap = Snap()
        p = self._param("snap", Action, actions=snap)
        w = create_param_widget(p)
        assert isinstance(w, mgw.LineEdit)

    def test_unresolvable_annotation_raises_not_lineedit(self) -> None:
        """create_param_widget raises RuntimeError for truly exotic annotations.

        This should never happen in normal operation (create_plan_spec guards
        against it), but we verify the contract here explicitly.
        """

        class Exotic:
            pass

        p = self._param("thing", Exotic)
        with pytest.raises((TypeError, ValueError, RuntimeError)):
            create_param_widget(p)
