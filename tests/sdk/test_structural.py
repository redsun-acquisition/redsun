from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from redsun._structural import members, methods, problems, satisfies


@runtime_checkable
class Greets(Protocol):
    label: str

    def greet(self, who: str, loudly: bool = False) -> str: ...

    @staticmethod
    def parse(raw: str) -> str: ...


class Compliant:
    label = "hi"

    def greet(self, who: str, loudly: bool = False) -> str:
        return who

    @staticmethod
    def parse(raw: str) -> str:
        return raw


class MissingData:
    def greet(self, who: str, loudly: bool = False) -> str:
        return who

    @staticmethod
    def parse(raw: str) -> str:
        return raw


class RenamedParameter:
    label = "hi"

    def greet(self, target: str, loudly: bool = False) -> str:
        return target

    @staticmethod
    def parse(raw: str) -> str:
        return raw


class ExtraRequired:
    label = "hi"

    def greet(self, who: str, loudly: bool, punctuation: str) -> str:
        return who

    @staticmethod
    def parse(raw: str) -> str:
        return raw


class ExtraDefaulted:
    label = "hi"

    def greet(self, who: str, loudly: bool = False, times: int = 1) -> str:
        return who

    @staticmethod
    def parse(raw: str) -> str:
        return raw


class NotCallable:
    label = "hi"
    greet = "not a method"

    @staticmethod
    def parse(raw: str) -> str:
        return raw


class NoGreet:
    label = "hi"

    @staticmethod
    def parse(raw: str) -> str:
        return raw


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (Compliant(), []),
        (ExtraDefaulted(), []),
        (MissingData(), ["'label' is missing"]),
        (NoGreet(), ["'greet' is missing"]),
        (NotCallable(), ["'greet' is not callable"]),
    ],
)
def test_problems_reports_each_reason(candidate: object, expected: list[str]) -> None:
    assert problems(candidate, Greets) == expected


@pytest.mark.parametrize("candidate", [RenamedParameter(), ExtraRequired()])
def test_signature_mismatch_names_both_calls(candidate: object) -> None:
    (reason,) = problems(candidate, Greets)
    assert reason.startswith("greet(")
    assert "cannot be called as greet(who, loudly=False)" in reason


def test_staticmethod_keeps_its_first_parameter() -> None:
    class WrongStatic:
        label = "hi"

        def greet(self, who: str, loudly: bool = False) -> str:
            return who

        @staticmethod
        def parse() -> str:
            return ""

    (reason,) = problems(WrongStatic(), Greets)
    assert "cannot be called as parse(raw)" in reason


def test_class_leaves_data_members_unchecked() -> None:
    assert problems(MissingData, Greets) == []
    assert problems(MissingData(), Greets) == ["'label' is missing"]


def test_members_and_methods_split_data_from_callables() -> None:
    """The split decides what a class can be checked for and what needs an instance."""
    assert members(Greets) == {"label", "greet", "parse"}
    assert methods(Greets) == {"greet", "parse"}


@runtime_checkable
class Named(Protocol):
    @property
    def name(self) -> str: ...


class NameAsProperty:
    @property
    def name(self) -> str:
        return "x"


class NameAsAttribute:
    def __init__(self) -> None:
        self.name = "x"


class Nameless:
    pass


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [(NameAsProperty(), True), (NameAsAttribute(), True), (Nameless(), False)],
)
def test_a_property_member_is_data_not_a_call(
    candidate: object, expected: bool
) -> None:
    """A protocol property is answered by any instance holding the name."""
    assert methods(Named) == frozenset()
    assert satisfies(candidate, Named) is expected
