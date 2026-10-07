from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable, Collection, Iterable, MutableMapping, Sequence
from collections.abc import Set as AbstractSet
from inspect import Parameter
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

import pytest
from annotated_types import Ge, Gt, Interval, Le, Len, MaxLen, MinLen, MultipleOf
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator

from redsun.engine.actions import PlanAction, continuous
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
from tests.sdk.mocks import DetectorProtocol, MotorProtocol, RoiDetector, XYStage, param

if TYPE_CHECKING:
    # deliberately never imported at runtime: a plan annotated with it
    # reproduces a plugin author hiding an import behind TYPE_CHECKING
    from decimal import Decimal


def _broken_default(frames: Annotated[int, Ge(1)] = 0) -> MsgGenerator[None]:
    yield from ()


def _option_dict(
    frames: Annotated[int, Ge(1), {"widget_type": "Slider"}] = 1,
) -> MsgGenerator[None]:
    yield from ()


@pytest.fixture
def mock_motor() -> XYStage:
    """Single mock motor device."""
    return XYStage("stage")


@pytest.fixture
def one_detector() -> dict[str, RoiDetector]:
    """Return a session's devices holding one detector, `cam`."""
    return {"cam": RoiDetector("cam")}


@pytest.fixture
def one_motor(mock_motor: XYStage) -> dict[str, XYStage]:
    """Return a session's devices holding one motor, `stage`."""
    return {"stage": mock_motor}


def _make_spec(*params: ParamDescription) -> PlanSpec:
    return PlanSpec(name="plan", docs="", parameters=list(params))


def limited(
    name: str, annotation: Any, default: Any = Parameter.empty
) -> ParamDescription:
    """Describe a parameter whose full annotation is *annotation*."""
    return ParamDescription(
        name=name,
        kind=ParamKind.POSITIONAL_OR_KEYWORD,
        annotation=annotation,
        default=default,
        annotated=annotation,
    )


@pytest.mark.parametrize(
    ("predicate", "annotation", "expected"),
    [
        (isdevice, DetectorProtocol, True),
        (isdevice, MotorProtocol, True),
        (isdevice, int, False),
        (isdevice, str, False),
        (isdevice, 42, False),
        (isdevicesequence, Sequence[DetectorProtocol], True),
        (isdevicesequence, Sequence[MotorProtocol], True),
        (isdevicesequence, Sequence[int], False),
        (isdevicesequence, DetectorProtocol, False),
        (isdeviceset, set[DetectorProtocol], True),
        (isdeviceset, AbstractSet[DetectorProtocol], True),
        (isdeviceset, frozenset[DetectorProtocol], True),
        (isdeviceset, set[int], False),
        (isdeviceset, DetectorProtocol, False),
        (isdeviceset, Sequence[DetectorProtocol], False),
        (issequence, Sequence[int], True),
        (issequence, list[float], True),
        (issequence, str, False),
        (issequence, int, False),
    ],
)
def test_the_annotation_predicates(
    predicate: Callable[[object], bool], annotation: object, expected: bool
) -> None:
    """Classify annotations as device, device sequence, device set or sequence."""
    assert predicate(annotation) is expected


@pytest.mark.parametrize(
    ("annotation", "hidden"),
    [
        (int, False),
        (list[int], False),
        (Iterable[int], False),
        (Collection[int], False),
        (tuple[int, str], False),
        (tuple[float, ...], False),
        (set[int], False),
        (frozenset[str], False),
        (MutableMapping[str, int], False),
        (dict[str, list[float]], False),
        (int | None, False),
        (float | list[float], False),
        (list[Annotated[float, {"min": -5.0}]], False),
        (dict[str, Annotated[int, "units"]], False),
        (deque[int], True),
        (OrderedDict[str, int], True),
        (Callable[[int], int], True),
        (Any, True),
        (dict[str, Any] | None, True),
        (dict[str, Readable[Any]], True),
        (Readable[Any] | None, True),
        (dict[list[int], int], True),
    ],
)
def test_a_parameter_with_a_default_is_hidden_when_no_widget_can_show_it(
    annotation: object, hidden: bool
) -> None:
    """Hide a parameter with a default that no widget can show, and show the rest."""

    def plan(x: object = None) -> MsgGenerator[None]:
        yield from ()

    plan.__annotations__["x"] = annotation

    [description] = create_plan_spec(plan, {}).parameters

    assert description.hidden is hidden


def test_an_unannotated_parameter_with_a_default_is_hidden() -> None:
    """Hide a parameter with a default and no annotation."""

    def plan(x: int = 5) -> MsgGenerator[None]:
        yield from ()

    del plan.__annotations__["x"]

    [description] = create_plan_spec(plan, {}).parameters

    assert description.hidden


def test_a_hidden_parameter_keeps_the_parameters_after_it_in_place() -> None:
    """Give a hidden parameter its default, so the values after it keep their places."""

    def plan(
        frames: int, md: dict[str, Any] | None = None, step: float = 1.0
    ) -> MsgGenerator[None]:
        yield from ()

    spec = create_plan_spec(plan, {})

    args, kwargs = collect_arguments(
        spec, resolve_arguments(spec, {"frames": 3, "step": 0.5}, {})
    )

    assert (args, kwargs) == ((3, None, 0.5), {})


class TestCreatePlanSpec:
    """Tests for `create_plan_spec` across the supported annotation shapes."""

    def test_int_param(self) -> None:
        """Describe an int parameter with no choices and no device protocol."""

        def plan(x: int) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        p = spec.parameters[0]
        assert p.name == "x"
        assert p.annotation is int
        assert p.choices is None
        assert p.device_proto is None

    def test_float_param_with_default(self) -> None:
        """Keep the default value of a float parameter."""

        def plan(step: float = 1.0) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        p = spec.parameters[0]
        assert p.has_default
        assert p.default == pytest.approx(1.0)

    def test_literal_produces_string_choices(self) -> None:
        """Turn a Literal of strings into single-select choices."""

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
        """Keep an empty sequence default as a default, not as a list of actions."""

        def plan(label: Sequence[str] = default) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})

        assert spec.parameters[0].actions is None
        assert spec.parameters[0].default == default

    def test_an_already_evaluated_annotation_is_taken_as_it_is(self) -> None:
        """Accept annotations already evaluated, as without the annotations import."""

        def plan(n=1):  # type: ignore[no-untyped-def]
            yield from ()

        plan.__annotations__ = {"n": int, "return": MsgGenerator[None]}

        spec = create_plan_spec(plan, {})

        assert spec.parameters[0].annotation is int

    def test_literal_values_are_kept_as_they_are(self) -> None:
        """Keep Literal values as they are, without turning them into strings."""

        def plan(n: Literal[1, 2, 3] = 1) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        assert spec.parameters[0].choices == [1, 2, 3]

    def test_single_device_param_populates_choices(
        self, one_motor: dict[str, XYStage]
    ) -> None:
        """Offer the names of matching devices as the choices of a device parameter."""

        def plan(motor: MotorProtocol) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, one_motor)
        p = spec.parameters[0]
        assert p.choices == ["stage"]
        assert not p.multiselect
        assert p.device_proto is MotorProtocol

    def test_single_device_no_registry_match_raises(self) -> None:
        """Refuse a required device parameter that no registered device matches."""

        def plan(motor: MotorProtocol) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})
        assert exc_info.value.param_name == "motor"

    def test_single_device_no_registry_match_ok_with_default(self) -> None:
        """Accept a device parameter with a default when no device matches."""

        def plan(motor: MotorProtocol = None) -> MsgGenerator[None]:  # type: ignore[assignment]
            yield from ()

        spec = create_plan_spec(plan, {})
        assert spec.parameters[0].choices is None  # no match, but has default

    def test_sequence_device_param_is_multiselect(
        self, one_detector: dict[str, RoiDetector]
    ) -> None:
        """Make a sequence of devices a multiple choice of the matching devices."""

        def plan(dets: Sequence[DetectorProtocol]) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.choices == ["cam"]
        assert p.multiselect
        assert p.device_proto is DetectorProtocol

    def test_set_device_param_is_multiselect(
        self, one_detector: dict[str, RoiDetector]
    ) -> None:
        """Make a set of devices a multiple choice of the matching devices."""

        def plan(dets: set[DetectorProtocol]) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.choices == ["cam"]
        assert p.multiselect
        assert p.device_proto is DetectorProtocol

    def test_var_positional_device_is_multiselect(
        self, one_detector: dict[str, RoiDetector]
    ) -> None:
        """Make a variadic positional device parameter a multiple choice."""

        def plan(*dets: DetectorProtocol) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, one_detector)
        p = spec.parameters[0]
        assert p.kind is ParamKind.VAR_POSITIONAL
        assert p.choices == ["cam"]
        assert p.multiselect

    def test_action_param_has_no_choices_and_stores_meta(self) -> None:
        """Store a PlanAction default as the parameter's action, with no choices."""

        def plan(
            frames: int = 1, /, snap: PlanAction = PlanAction(name="snap")
        ) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        action_p = next(p for p in spec.parameters if p.name == "snap")
        assert action_p.actions == PlanAction(name="snap")
        assert action_p.choices is None

    def test_action_sequence_param(self) -> None:
        """Store a list of PlanAction defaults as the parameter's actions."""

        def plan(
            frames: int = 1,
            /,
            actions: PlanAction = [PlanAction(name="a"), PlanAction(name="b")],  # type: ignore[assignment]
        ) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        p = next(q for q in spec.parameters if q.name == "actions")
        assert p.actions == [PlanAction(name="a"), PlanAction(name="b")]

    def test_two_actions_of_one_name_are_refused(self) -> None:
        """Refuse a plan declaring two actions with the same name."""

        def plan(
            snap: PlanAction = PlanAction(name="snap"),
            again: PlanAction = PlanAction(name="snap", description="another"),
        ) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(
            ValueError, match="declares more than one action named 'snap'"
        ):
            create_plan_spec(plan, {})

    @pytest.mark.parametrize(
        ("mark", "pausable"),
        [
            pytest.param(continuous, False, id="bare"),
            pytest.param(continuous(), False, id="called"),
            pytest.param(continuous(pausable=True), True, id="pausable"),
        ],
    )
    def test_a_continuous_plan_is_reported(
        self,
        mark: Callable[
            [Callable[[], MsgGenerator[None]]], Callable[[], MsgGenerator[None]]
        ],
        pausable: bool,
    ) -> None:
        """Report a plan marked continuous, and whether it can be paused."""

        @mark
        def plan() -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        assert spec.continuous is True
        assert spec.pausable is pausable

    def test_an_unmarked_plan_is_not_continuous(self) -> None:
        """Report an unmarked plan as neither continuous nor pausable."""

        def plan(x: int) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(plan, {})
        assert spec.continuous is False
        assert spec.pausable is False

    def test_self_is_stripped_from_method_signature(self) -> None:
        """Leave self out of the parameters of a plan defined as a method."""

        class Presenter:
            def plan(self, x: int) -> MsgGenerator[None]:
                yield from ()

        spec = create_plan_spec(Presenter.plan, {})
        assert all(p.name != "self" for p in spec.parameters)
        assert spec.parameters[0].name == "x"

    def test_non_generator_raises_type_error(self) -> None:
        """Raise TypeError for a plan that is not a generator function."""

        def not_a_plan(x: int) -> int:
            return x

        with pytest.raises(TypeError, match="generator function"):
            create_plan_spec(not_a_plan, {})  # type: ignore[arg-type]

    def test_missing_return_annotation_raises(self) -> None:
        """Raise TypeError for a plan with no return annotation."""

        def plan(x: int):  # type: ignore[no-untyped-def]
            yield from ()

        with pytest.raises(TypeError, match="return type annotation"):
            create_plan_spec(plan, {})

    def test_wrong_return_type_raises(self) -> None:
        """Raise TypeError for a plan whose return type is not MsgGenerator."""

        def plan(x: int) -> list[int]:  # type: ignore[misc]
            yield x

        with pytest.raises(TypeError, match="MsgGenerator"):
            create_plan_spec(plan, {})  # type: ignore[arg-type]


class TestUnresolvableAnnotation:
    """Tests for the unresolvable-annotation guard."""

    class _Exotic:
        """A type magicgui has no idea how to handle."""

    def test_required_exotic_param_raises(self) -> None:
        """Refuse a required parameter whose type has no widget."""

        def bad_plan(thing: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(bad_plan, {})

        err = exc_info.value
        assert err.param_name == "thing"
        assert err.plan_name == "bad_plan"
        assert err.annotation is TestUnresolvableAnnotation._Exotic

    def test_optional_exotic_param_does_not_raise(self) -> None:
        """Accept a parameter whose type has no widget when it has a default."""
        default_val = TestUnresolvableAnnotation._Exotic()

        def ok_plan(
            thing: TestUnresolvableAnnotation._Exotic = default_val,
        ) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(ok_plan, {})
        assert spec.parameters[0].name == "thing"

    def test_var_keyword_exotic_does_not_raise(self) -> None:
        """Accept a **kwargs parameter whose type has no widget."""

        def ok_plan(**kw: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield from ()

        spec = create_plan_spec(ok_plan, {})
        assert spec.parameters[0].kind is ParamKind.VAR_KEYWORD

    def test_error_message_contains_plan_and_param_name(self) -> None:
        """Name the plan and the parameter in the error message."""

        def broken(widget: TestUnresolvableAnnotation._Exotic) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError, match="broken") as exc_info:
            create_plan_spec(broken, {})

        assert "widget" in str(exc_info.value)
        assert "broken" in str(exc_info.value)


class TestTypeCheckingOnlyAnnotation:
    """A name available only to a type checker is reported, not raised as NameError."""

    def test_required_param_raises_unresolvable(self) -> None:
        """Refuse a parameter annotated with a name imported for type checking only."""

        def plan(amount: Decimal) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})

        err = exc_info.value
        assert err.plan_name == "plan"
        assert err.param_name == "amount"
        assert err.annotation == "Decimal"

    def test_unresolvable_return_raises_unresolvable(self) -> None:
        """Refuse a return annotation naming a type imported for type checking only."""

        def plan(count: int) -> Decimal:  # type: ignore[misc]
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})  # type: ignore[arg-type]

        assert exc_info.value.param_name == "return"

    def test_resolvable_siblings_do_not_mask_the_bad_one(self) -> None:
        """Name the unresolvable parameter in the error, not the first parameter."""

        def plan(count: int, path: Path, amount: Decimal) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError) as exc_info:
            create_plan_spec(plan, {})

        assert exc_info.value.param_name == "amount"

    def test_optional_unresolvable_param_still_raises(self) -> None:
        """Refuse an unresolvable annotation even when the parameter has a default."""

        def plan(amount: Decimal | None = None) -> MsgGenerator[None]:
            yield from ()

        with pytest.raises(UnresolvableAnnotationError):
            create_plan_spec(plan, {})


class TestCollectArguments:
    """Tests for `collect_arguments`."""

    def test_positional_only(self) -> None:
        """Pass a positional-only parameter positionally."""
        spec = _make_spec(param("x", kind=ParamKind.POSITIONAL_ONLY))
        args, kwargs = collect_arguments(spec, {"x": 42})
        assert args == (42,)
        assert kwargs == {}

    def test_positional_or_keyword(self) -> None:
        """Pass a positional-or-keyword parameter positionally."""
        spec = _make_spec(param("x", kind=ParamKind.POSITIONAL_OR_KEYWORD))
        args, kwargs = collect_arguments(spec, {"x": 7})
        assert args == (7,)
        assert kwargs == {}

    def test_keyword_only(self) -> None:
        """Pass a keyword-only parameter by keyword."""
        spec = _make_spec(param("n", kind=ParamKind.KEYWORD_ONLY))
        args, kwargs = collect_arguments(spec, {"n": 3})
        assert args == ()
        assert kwargs == {"n": 3}

    def test_var_positional_sequence_expanded(self) -> None:
        """Expand a sequence given for *args into separate positional arguments."""
        spec = _make_spec(param("vals", kind=ParamKind.VAR_POSITIONAL))
        args, _kwargs = collect_arguments(spec, {"vals": [1, 2, 3]})
        assert args == (1, 2, 3)

    def test_var_positional_single_value_wrapped(self) -> None:
        """Pass a single value given for *args as one positional argument."""
        spec = _make_spec(param("vals", kind=ParamKind.VAR_POSITIONAL))
        args, _kwargs = collect_arguments(spec, {"vals": 99})
        assert args == (99,)

    def test_var_keyword_mapping_merged(self) -> None:
        """Merge a mapping given for **kwargs into the keyword arguments."""
        spec = _make_spec(param("kw", kind=ParamKind.VAR_KEYWORD))
        _args, kwargs = collect_arguments(spec, {"kw": {"a": 1, "b": 2}})
        assert kwargs == {"a": 1, "b": 2}

    def test_var_keyword_non_mapping_raises(self) -> None:
        """Raise TypeError when **kwargs is given something other than a mapping."""
        spec = _make_spec(param("kw", kind=ParamKind.VAR_KEYWORD))
        with pytest.raises(TypeError, match="Mapping"):
            collect_arguments(spec, {"kw": "not_a_mapping"})

    def test_missing_param_skipped(self) -> None:
        """Skip a parameter that has no value."""
        spec = _make_spec(
            param("x", kind=ParamKind.POSITIONAL_OR_KEYWORD),
            param("y", kind=ParamKind.POSITIONAL_OR_KEYWORD),
        )
        args, _kwargs = collect_arguments(spec, {"x": 1})
        assert args == (1,)

    def test_ordering_preserved(self) -> None:
        """Keep positional arguments in the order the plan declares them."""
        spec = _make_spec(
            param("a", kind=ParamKind.POSITIONAL_OR_KEYWORD),
            param("b", kind=ParamKind.POSITIONAL_OR_KEYWORD),
            param("c", kind=ParamKind.POSITIONAL_OR_KEYWORD),
        )
        args, _ = collect_arguments(spec, {"c": 3, "a": 1, "b": 2})
        assert args == (1, 2, 3)


class TestResolveArguments:
    """Tests for `resolve_arguments`."""

    def test_non_device_param_passed_through(self) -> None:
        """Pass a parameter that is not a device through unchanged."""
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
        """Fill in a missing action parameter with its declared action."""
        action_instance = PlanAction(name="go")
        spec = _make_spec(
            ParamDescription(
                name="go",
                kind=ParamKind.POSITIONAL_ONLY,
                annotation=PlanAction,
                default=action_instance,
                actions=action_instance,
            )
        )
        resolved = resolve_arguments(spec, {}, {})
        assert resolved["go"] is action_instance

    def test_action_not_overwritten_when_present(self) -> None:
        """Keep an action given for an action parameter."""
        a1 = PlanAction(name="go")
        a2 = PlanAction(name="go")
        spec = _make_spec(
            ParamDescription(
                name="go",
                kind=ParamKind.POSITIONAL_ONLY,
                annotation=PlanAction,
                default=a1,
                actions=a1,
            )
        )
        resolved = resolve_arguments(spec, {"go": a2}, {})
        assert resolved["go"] is a2

    def test_single_device_label_resolved(self, one_motor: dict[str, XYStage]) -> None:
        """Replace a device name with the device it names."""
        spec = _make_spec(
            ParamDescription(
                name="motor",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=MotorProtocol,
                default=Parameter.empty,
                choices=["stage"],
                device_proto=MotorProtocol,
            )
        )
        resolved = resolve_arguments(spec, {"motor": "stage"}, one_motor)
        assert resolved["motor"] is one_motor["stage"]

    def test_device_sequence_labels_resolved(
        self, one_detector: dict[str, RoiDetector]
    ) -> None:
        """Replace a list of device names with a list of the devices."""
        spec = _make_spec(
            ParamDescription(
                name="dets",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=Sequence[DetectorProtocol],
                default=Parameter.empty,
                choices=["cam"],
                multiselect=True,
                device_proto=DetectorProtocol,
            )
        )
        resolved = resolve_arguments(spec, {"dets": ["cam"]}, one_detector)
        assert resolved["dets"] == [one_detector["cam"]]

    def test_device_set_labels_resolved(
        self, one_detector: dict[str, RoiDetector]
    ) -> None:
        """Replace device names with a set of the devices for a set parameter."""
        spec = _make_spec(
            ParamDescription(
                name="dets",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=set[DetectorProtocol],
                default=Parameter.empty,
                choices=["cam"],
                multiselect=True,
                device_proto=DetectorProtocol,
            )
        )
        resolved = resolve_arguments(spec, {"dets": ["cam"]}, one_detector)
        assert resolved["dets"] == {one_detector["cam"]}

    def test_unknown_label_resolves_to_none_for_single(
        self, one_motor: dict[str, XYStage]
    ) -> None:
        """Resolve an unknown device name to None."""
        spec = _make_spec(
            ParamDescription(
                name="motor",
                kind=ParamKind.POSITIONAL_OR_KEYWORD,
                annotation=MotorProtocol,
                default=Parameter.empty,
                choices=["stage"],
                device_proto=MotorProtocol,
            )
        )
        resolved = resolve_arguments(spec, {"motor": "nonexistent"}, one_motor)
        assert resolved["motor"] is None


@pytest.mark.parametrize(
    ("annotation", "listed"),
    [
        pytest.param(Readable[Any], False, id="single"),
        pytest.param(Sequence[Readable[Any]], True, id="sequence"),
    ],
)
def test_a_protocol_given_type_arguments_offers_and_resolves_its_devices(
    annotation: Any, listed: bool, one_detector: dict[str, RoiDetector]
) -> None:
    """Offer and resolve the devices of a protocol written with type arguments."""

    def plan(dets: Any) -> MsgGenerator[None]:
        yield from ()

    plan.__annotations__["dets"] = annotation

    spec = create_plan_spec(plan, one_detector)
    resolved = resolve_arguments(spec, {"dets": ["cam"]}, one_detector)

    assert spec.parameters[0].choices == ["cam"]
    assert spec.parameters[0].device_proto is Readable
    camera = one_detector["cam"]
    assert resolved["dets"] == ([camera] if listed else camera)


@pytest.mark.parametrize(
    ("annotation", "value", "lines"),
    [
        (Annotated[int, Ge(1)], 0, ["p: Input should be greater than or equal to 1"]),
        (Annotated[int, Ge(1)], 1, []),
        (Annotated[float, Gt(0), Le(10)], 0.0, ["p: Input should be greater than 0"]),
        (
            Annotated[float, Gt(0), Le(10)],
            11.0,
            ["p: Input should be less than or equal to 10"],
        ),
        (
            Annotated[float, Interval(ge=-1, lt=1)],
            1.0,
            ["p: Input should be less than 1"],
        ),
        (Annotated[float, MultipleOf(0.001)], 0.003, []),
        (Annotated[int, MultipleOf(2)], 3, ["p: Input should be a multiple of 2"]),
        (
            Annotated[str, MinLen(1)],
            "",
            ["p: String should have at least 1 character"],
        ),
        (
            Annotated[list[float], MaxLen(2)],
            [1.0, 2.0, 3.0],
            ["p: List should have at most 2 items after validation, not 3"],
        ),
        (
            Annotated[list[float], Len(2, 3)],
            [1.0],
            ["p: List should have at least 2 items after validation, not 1"],
        ),
        (
            list[Annotated[int, Ge(0)]],
            [1, -1],
            ["p[1]: Input should be greater than or equal to 0"],
        ),
        (
            dict[str, list[Annotated[int, Ge(0)]]],
            {"a": [1, -2]},
            ["p['a'][1]: Input should be greater than or equal to 0"],
        ),
        (Annotated[float, Gt(0)] | None, None, []),
        (Annotated[float, Gt(0)] | None, 0.0, ["p: Input should be greater than 0"]),
        (
            Annotated[float, Gt(0)] | list[Annotated[float, Ge(0)]],
            0.0,
            ["p: Input should be greater than 0"],
        ),
        (
            Annotated[float, Gt(0)] | list[Annotated[float, Ge(0)]],
            [1.0, -1.0],
            ["p[1]: Input should be greater than or equal to 0"],
        ),
        (Annotated[int, Ge(1)], "x", ["p: Input should be a valid integer"]),
        (int, -5, []),
    ],
)
def test_a_value_is_checked_against_its_limits(
    annotation: Any, value: Any, lines: list[str]
) -> None:
    """Report each limit a value breaks, located inside it, and nothing for a value within them."""
    assert limited("p", annotation).problems(value) == lines


def test_a_limit_that_cannot_apply_to_its_type_is_a_problem() -> None:
    """Report a limit that does not fit its type as a problem instead of raising."""
    [line] = limited("p", Annotated[dict[str, int], Ge(0)]).problems({"a": 1})

    assert line.startswith("p: ")
    assert "ge" in line


def test_a_limit_that_cannot_be_built_is_refused() -> None:
    """Refuse a parameter whose limit cannot be built, with a TypeError naming it."""
    with pytest.raises(TypeError, match="'p'"):
        limited("p", Annotated[int, Ge("a")])


def test_a_default_breaking_its_limits_refuses_the_plan() -> None:
    """Refuse a plan whose default breaks its own limits, naming the parameter."""
    with pytest.raises(
        ValueError, match="the default of 'frames' breaks its own limits"
    ):
        create_plan_spec(_broken_default, {})


def test_the_spec_keeps_the_whole_annotation() -> None:
    """Keep the outer Annotated metadata, option dict included, beside the bare type."""
    [frames] = create_plan_spec(_option_dict, {}).parameters

    assert frames.annotation is int
    assert frames.annotated == Annotated[int, Ge(1), {"widget_type": "Slider"}]


def test_resolving_a_value_outside_its_limits_is_refused() -> None:
    """Refuse values outside their limits, listing every broken one."""
    spec = _make_spec(
        limited("frames", Annotated[int, Ge(1)]),
        limited("exposure", Annotated[float, Gt(0)]),
    )

    with pytest.raises(ValueError) as caught:
        resolve_arguments(spec, {"frames": 0, "exposure": 0.0}, {})

    assert str(caught.value) == (
        "frames: Input should be greater than or equal to 1; "
        "exposure: Input should be greater than 0"
    )


def test_a_device_parameter_is_never_checked_against_limits() -> None:
    """Leave a device parameter's chosen names unchecked, whatever limits it carries."""
    detectors = ParamDescription(
        name="detectors",
        kind=ParamKind.POSITIONAL_OR_KEYWORD,
        annotation=Sequence[Readable[Any]],
        default=Parameter.empty,
        device_proto=Readable,
        annotated=Annotated[Sequence[Readable[Any]], MinLen(1)],
    )

    assert detectors.problems(["cam"]) == []


@pytest.mark.parametrize(
    ("kind", "value", "lines"),
    [
        (ParamKind.VAR_POSITIONAL, (1.0, 2.0), []),
        (
            ParamKind.VAR_POSITIONAL,
            (1.0, -2.0),
            ["values[1]: Input should be greater than or equal to 0"],
        ),
        (
            ParamKind.VAR_POSITIONAL,
            -2.0,
            ["values: Input should be greater than or equal to 0"],
        ),
        (ParamKind.VAR_KEYWORD, {"a": 1.0}, []),
        (
            ParamKind.VAR_KEYWORD,
            {"a": 1.0, "b": -1.0},
            ["values['b']: Input should be greater than or equal to 0"],
        ),
    ],
)
def test_each_value_of_a_variadic_parameter_is_checked(
    kind: ParamKind, value: Any, lines: list[str]
) -> None:
    """Check each item of *args and each value of **kwargs against the limits, not the whole."""
    values = ParamDescription(
        name="values",
        kind=kind,
        annotation=float,
        default=Parameter.empty,
        annotated=Annotated[float, Ge(0)],
    )

    assert values.problems(value) == lines
