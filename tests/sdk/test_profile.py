"""A session profiles its start or its whole run when asked, and refuses what it cannot do."""

from __future__ import annotations

import sys

import pytest

from redsun import Session


class Empty(Session):
    pass


@pytest.mark.parametrize(
    ("keywords", "error", "message"),
    [
        ({"profile": "Start"}, ValueError, "'start', 'run'"),
        ({"profile": "always"}, ValueError, "'start', 'run'"),
        ({"profile_dir": "profiles"}, TypeError, "given without profile"),
    ],
)
def test_a_profile_the_session_cannot_take_is_refused(
    keywords: dict[str, str], error: type[Exception], message: str
) -> None:
    """Refuse an unknown profile kind, and a profile folder with no profile."""
    with pytest.raises(error, match=message):
        Empty(**keywords)  # type: ignore[arg-type]


def test_a_profile_without_the_extra_names_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse a profile when `pyinstrument` is missing, naming the extra."""
    monkeypatch.setitem(sys.modules, "pyinstrument", None)

    with pytest.raises(ImportError, match=r"redsun\[profile\]"):
        Empty(profile="start")
