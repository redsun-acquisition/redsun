"""Widgets for plan parameters whose values are built from other values.

Each widget subclasses `magicgui`'s `ValuedContainerWidget`, has a `value` of
the annotated type and a `problems` list, and builds its inner widgets with
`create_value_widget`, so the shapes nest to any depth.
"""

from __future__ import annotations

from types import NoneType
from typing import TYPE_CHECKING, Any, Literal, get_args, get_origin

from magicgui import widgets as mgw
from magicgui.types import Undefined
from magicgui.widgets.bases import ValuedContainerWidget, Widget

from ...presenter._shapes import (
    container_type,
    is_fixed_tuple,
    is_mapping,
    union_members,
    without_none,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


def problems_of(widget: Any) -> list[str]:
    """Return what makes *widget*'s value invalid; a `magicgui` widget reports nothing."""
    return list(getattr(widget, "problems", []))


def type_name(ann: Any) -> str:
    """Return a short name for *ann*, as a union lists its members: `list of float`."""
    built = container_type(ann)
    if built is not None:
        return f"{built.__name__} of {type_name(get_args(ann)[0])}"
    return getattr(ann, "__name__", repr(ann))


def create_value_widget(ann: Any, value: Any = Undefined, name: str = "") -> Any:
    """Build the widget showing a value of type *ann*, starting from *value*."""
    if get_origin(ann) is Literal:
        choices = list(get_args(ann))
        return mgw.ComboBox(
            name=name, choices=choices, value=value if value in choices else choices[0]
        )
    members = union_members(ann)
    if NoneType in members:
        return OptionalEdit(without_none(members), value, name=name)
    if members:
        return UnionEdit(members, value, name=name)
    if is_mapping(ann):
        return MappingEdit(ann, value, name=name)
    if is_fixed_tuple(ann):
        return FixedTupleEdit(ann, value, name=name)
    if container_type(ann) is not None:
        return SequenceEdit(ann, value, name=name)
    # without a value magicgui gets its sentinel rather than None: a widget
    # that cannot hold None, such as the CheckBox built for a bool, raises on
    # being handed one
    return mgw.create_widget(annotation=ann, name=name, value=value)


def holds(ann: Any, value: Any) -> bool:
    """Return True if *value* is of the built-in type a widget for *ann* returns."""
    if get_origin(ann) is Literal:
        return value in get_args(ann)
    built = container_type(ann) or (
        dict if is_mapping(ann) else tuple if is_fixed_tuple(ann) else ann
    )
    try:
        return isinstance(value, built)
    except TypeError:
        return False


class OptionalEdit(ValuedContainerWidget[Any]):
    """A "set" checkbox beside the widget for a value that may be `None`."""

    def __init__(self, inner: Any, value: Any = Undefined, name: str = "") -> None:
        given = value is not Undefined and value is not None
        self._set = mgw.CheckBox(text="set", value=given)
        self._inner = create_value_widget(inner, value if given else Undefined)
        self._inner.enabled = given
        super().__init__(
            name=name,
            layout="horizontal",
            labels=False,
            widgets=[self._set, self._inner],
        )
        self.margins = (0, 0, 0, 0)
        self._set.changed.connect(self._on_set)
        self._inner.changed.connect(lambda _: self.changed.emit(self.value))

    def _on_set(self, ticked: bool) -> None:
        self._inner.enabled = ticked
        self.changed.emit(self.value)

    def get_value(self) -> Any:
        """Return `None` while unticked, else the inner widget's value."""
        return self._inner.value if self._set.value else None

    def set_value(self, value: Any) -> None:
        """Untick for `None`, else tick and show *value*."""
        self._set.value = value is not None
        if value is not None:
            self._inner.value = value

    @property
    def problems(self) -> list[str]:
        """The inner widget's problems while ticked."""
        return problems_of(self._inner) if self._set.value else []


class UnionEdit(ValuedContainerWidget[Any]):
    """A choice of member type above the widget for the chosen member.

    Starts on the member the default is an instance of, else on the first.
    """

    def __init__(
        self, members: tuple[Any, ...], value: Any = Undefined, name: str = ""
    ) -> None:
        self._members = members
        start = next(
            (
                i
                for i, member in enumerate(members)
                if value is not Undefined and holds(member, value)
            ),
            0,
        )
        names = [type_name(member) for member in members]
        self._choice = mgw.ComboBox(choices=names, value=names[start])
        self._edits = [
            create_value_widget(member, value if i == start else Undefined)
            for i, member in enumerate(members)
        ]
        super().__init__(name=name, labels=False, widgets=[self._choice, *self._edits])
        self.margins = (0, 0, 0, 0)
        self._show(start)
        self._choice.changed.connect(lambda _: self._on_choice())
        for edit in self._edits:
            edit.changed.connect(lambda _: self.changed.emit(self.value))

    def _chosen(self) -> int:
        return list(self._choice.choices).index(self._choice.value)

    def _show(self, index: int) -> None:
        for i, edit in enumerate(self._edits):
            edit.visible = i == index

    def _on_choice(self) -> None:
        self._show(self._chosen())
        self.changed.emit(self.value)

    def get_value(self) -> Any:
        """Return the chosen member's value."""
        return self._edits[self._chosen()].value

    def set_value(self, value: Any) -> None:
        """Choose the member *value* belongs to, and show it."""
        for i, member in enumerate(self._members):
            if holds(member, value):
                self._choice.value = self._choice.choices[i]
                self._edits[i].value = value
                return

    @property
    def problems(self) -> list[str]:
        """The chosen member's problems."""
        return problems_of(self._edits[self._chosen()])


class Row(mgw.Container[Widget]):
    """One row of a list or mapping editor: its widgets and a remove button."""

    def __init__(self, edits: list[Any]) -> None:
        self.edits = edits
        self.remove_button = mgw.PushButton(text="-")
        super().__init__(
            layout="horizontal", labels=False, widgets=[*edits, self.remove_button]
        )
        self.margins = (0, 0, 0, 0)


class SequenceEdit(ValuedContainerWidget[Any]):
    """Rows of one element type, each removable, and a button adding one.

    Returns a `list`, `tuple`, `set` or `frozenset`, as the annotation names;
    a repeated item in a set is dropped.
    """

    def __init__(self, ann: Any, value: Any = Undefined, name: str = "") -> None:
        self._element = get_args(ann)[0]
        self._built = container_type(ann)
        self._add = mgw.PushButton(text="+")
        super().__init__(name=name, labels=False, widgets=[self._add])
        self.margins = (0, 0, 0, 0)
        self._rows: list[Row] = []
        self._add.changed.connect(lambda _: self._append())
        for item in [] if value is Undefined else value:
            self._append(item)

    def _append(self, item: Any = Undefined) -> None:
        edit = create_value_widget(self._element, item)
        row = Row([edit])
        row.remove_button.changed.connect(lambda _: self._remove(row))
        edit.changed.connect(lambda _: self.changed.emit(self.value))
        self._rows.append(row)
        self._insert_widget(len(self._rows) - 1, row)
        self.changed.emit(self.value)

    def _remove(self, row: Row) -> None:
        index = self._rows.index(row)
        self._rows.pop(index)
        self._pop_widget(index)
        self.changed.emit(self.value)

    def get_value(self) -> Any:
        """Return the rows' values in the built-in the annotation names."""
        assert self._built is not None
        return self._built(row.edits[0].value for row in self._rows)

    def set_value(self, value: Iterable[Any]) -> None:
        """Replace every row by one per item of *value*."""
        while self._rows:
            self._remove(self._rows[-1])
        for item in value:
            self._append(item)

    @property
    def problems(self) -> list[str]:
        """Each row's problems, prefixed with its position."""
        return [
            f"[{i}]: {problem}"
            for i, row in enumerate(self._rows)
            for problem in problems_of(row.edits[0])
        ]


class MappingEdit(ValuedContainerWidget[dict[Any, Any]]):
    """Key and value rows, each removable, and a button adding one.

    A key that repeats another is reported in `problems`.
    """

    def __init__(self, ann: Any, value: Any = Undefined, name: str = "") -> None:
        self._key, self._value = get_args(ann)
        self._add = mgw.PushButton(text="+")
        super().__init__(name=name, labels=False, widgets=[self._add])
        self.margins = (0, 0, 0, 0)
        self._rows: list[Row] = []
        self._add.changed.connect(lambda _: self._append())
        for key, item in ({} if value is Undefined else dict(value)).items():
            self._append(key, item)

    def _append(self, key: Any = Undefined, item: Any = Undefined) -> None:
        key_edit = create_value_widget(self._key, key)
        value_edit = create_value_widget(self._value, item)
        row = Row([key_edit, value_edit])
        row.remove_button.changed.connect(lambda _: self._remove(row))
        key_edit.changed.connect(lambda _: self.changed.emit(self.value))
        value_edit.changed.connect(lambda _: self.changed.emit(self.value))
        self._rows.append(row)
        self._insert_widget(len(self._rows) - 1, row)
        self.changed.emit(self.value)

    def _remove(self, row: Row) -> None:
        index = self._rows.index(row)
        self._rows.pop(index)
        self._pop_widget(index)
        self.changed.emit(self.value)

    def _repeated(self) -> set[Any]:
        keys = [row.edits[0].value for row in self._rows]
        return {key for key in keys if keys.count(key) > 1}

    def get_value(self) -> dict[Any, Any]:
        """Return the rows as a dict; of two rows with one key, the later one."""
        return {row.edits[0].value: row.edits[1].value for row in self._rows}

    def set_value(self, value: Mapping[Any, Any]) -> None:
        """Replace every row by one per entry of *value*."""
        while self._rows:
            self._remove(self._rows[-1])
        for key, item in value.items():
            self._append(key, item)

    @property
    def problems(self) -> list[str]:
        """Repeated keys, an empty text key, then each value's problems by key."""
        found = [
            f"duplicate key: {key!r}" for key in sorted(self._repeated(), key=repr)
        ]
        if any(row.edits[0].value == "" for row in self._rows):
            found.append("empty key")
        for row in self._rows:
            found.extend(
                f"[{row.edits[0].value!r}]: {problem}"
                for problem in problems_of(row.edits[1])
            )
        return found


class FixedTupleEdit(ValuedContainerWidget[tuple[Any, ...]]):
    """One widget per member of a fixed-length tuple."""

    def __init__(self, ann: Any, value: Any = Undefined, name: str = "") -> None:
        members = get_args(ann)
        items = [Undefined] * len(members) if value is Undefined else list(value)
        self._edits = [
            create_value_widget(member, item)
            for member, item in zip(members, items, strict=True)
        ]
        super().__init__(
            name=name, layout="horizontal", labels=False, widgets=self._edits
        )
        self.margins = (0, 0, 0, 0)
        for edit in self._edits:
            edit.changed.connect(lambda _: self.changed.emit(self.value))

    def get_value(self) -> tuple[Any, ...]:
        """Return the members' values as a tuple."""
        return tuple(edit.value for edit in self._edits)

    def set_value(self, value: Iterable[Any]) -> None:
        """Show each item of *value* in its member's widget."""
        for edit, item in zip(self._edits, value, strict=True):
            edit.value = item

    @property
    def problems(self) -> list[str]:
        """Each member's problems, prefixed with its position."""
        return [
            f"[{i}]: {problem}"
            for i, edit in enumerate(self._edits)
            for problem in problems_of(edit)
        ]
