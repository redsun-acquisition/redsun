from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from redsun.containers._structural import problems


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
