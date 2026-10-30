"""The fixtures `redsun.testing` gives a suite keep each test to itself."""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING

import pytest

from redsun import Session
from tests.sdk.helpers import automatic_collection

if TYPE_CHECKING:
    from pathlib import Path

    from redsun.testing import BuildSession

pytest_plugins = ["pytester"]

TWO_SESSIONS = """
from pathlib import Path

from redsun import Session


def refuse() -> None:
    raise RuntimeError("the second session could not stop")


def test_two_sessions(build):
    first = build(Session, {{"session": "first"}})
    first.on_release(Path({marker!r}).touch)
    second = build(Session, {{"session": "second"}})
    second.on_release(refuse)
"""
"""A test building two sessions, whose second refuses to shut down."""

BOTH_REFUSE = """
from redsun import Session


def refuse(which: str) -> None:
    raise RuntimeError(f"the {which} session could not stop")


def test_two_sessions(build):
    first = build(Session, {"session": "first"})
    first.on_release(lambda: refuse("first"))
    second = build(Session, {"session": "second"})
    second.on_release(lambda: refuse("second"))
"""
"""A test building two sessions, both refusing to shut down."""

COLLECTION_IS_OFF = """
import gc


def test_collection_is_off():
    assert not gc.isenabled()
"""
"""A test checking that automatic collection is off while it runs."""

LEAVES_A_CYCLE = """
import weakref
from pathlib import Path


class Cycle:
    def __init__(self):
        self.me = self


def test_leaves_a_cycle():
    weakref.finalize(Cycle(), Path({marker!r}).touch)
"""
"""A test leaving a reference cycle, whose collection touches a file."""

FINDS_IT_FREED = """
from pathlib import Path


def test_the_cycle_was_freed():
    assert Path({marker!r}).exists()
"""
"""A test of a later module, passing once the cycle was collected."""

TURNS_COLLECTION_ON = """
import gc


def test_before():
    assert not gc.isenabled()


def test_turns_collection_on():
    gc.enable()


def test_after():
    assert not gc.isenabled()
"""
"""Three tests, the second turning automatic collection on and leaving it on."""

KEEPS_ITS_SESSION = """
from redsun import Session

KEPT = []


def test_keeps_its_session(build):
    KEPT.append(build(Session, {"session": "kept"}))
"""
"""A test keeping the session it built in a list at module level."""

FIXTURE_RETURNS_IT = """
import pytest

from redsun import Session


@pytest.fixture
def app(build):
    return build(Session, {"session": "from-a-fixture"})


def test_uses_the_session(app):
    assert app.name == "from-a-fixture"
"""
"""A test receiving its session from a fixture, which `pytest` holds until the test's report."""

FAILS_TO_BUILD = """
from redsun import AsPresenter, Session


class Broken:
    def __init__(self, name: str) -> None:
        raise RuntimeError("this presenter cannot be built")


class BrokenApp(Session):
    ctrl: AsPresenter[Broken]


def test_builds_a_broken_presenter(build):
    session = build(BrokenApp, {"session": "broken"})
    assert "ctrl" not in session.presenters
"""
"""A test whose session logs the exception of a presenter that fails to build."""

LOGS_AT_SHUTDOWN = """
import logging

from redsun import AsPresenter, Session


class Closing:
    def __init__(self, name: str) -> None:
        self.name = name

    def shutdown(self) -> None:
        try:
            raise RuntimeError("closing failed")
        except RuntimeError:
            logging.getLogger("redsun").exception("could not close")


class ClosingApp(Session):
    ctrl: AsPresenter[Closing]


def test_shuts_down(build):
    session = build(ClosingApp, {"session": "closing"})
    assert "ctrl" in session.presenters
"""
"""A test whose presenter logs an exception while the session shuts down."""

RAISES = """
import pytest

from redsun import Session


def test_fails(build):
    session = build(Session, {"session": "failing"})
    assert session.name == "another"


@pytest.mark.xfail(strict=True)
def test_fails_as_expected(build):
    session = build(Session, {"session": "expected-to-fail"})
    assert session.name == "another"
"""
"""A failing test and an expected failure, each keeping its session in its traceback."""


def test_a_session_keeps_its_settings_under_tmp_path(
    tmp_path: Path, build: BuildSession
) -> None:
    """Open a session's settings in `tmp_path` without requesting `config_home`."""
    session = build(Session, {"session": "kept-to-the-test"})

    assert session.settings.path.is_relative_to(tmp_path / "config")


def test_every_session_is_shut_down_when_one_refuses(
    pytester: pytest.Pytester,
) -> None:
    """Shut the earlier session down when a later one raises, then report the error."""
    marker = pytester.path / "first-shut-down"
    pytester.makepyfile(TWO_SESSIONS.format(marker=str(marker)))

    result = pytester.runpytest("-p", "redsun.testing")

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(["E * RuntimeError: the second session could not stop"])
    result.stdout.no_fnmatch_line("*ExceptionGroup*")
    assert marker.exists()


def test_every_refusal_is_reported(pytester: pytest.Pytester) -> None:
    """Report in one group the error of every session refusing to shut down."""
    pytester.makepyfile(BOTH_REFUSE)

    result = pytester.runpytest("-p", "redsun.testing")

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(
        [
            "*ExceptionGroup: sessions could not shut down (2 sub-exceptions)*",
            "*the second session could not stop*",
            "*the first session could not stop*",
        ]
    )


def test_automatic_collection_is_off_during_a_run(pytester: pytest.Pytester) -> None:
    """Run every test with automatic collection off, and restore it after the run."""
    pytester.makepyfile(COLLECTION_IS_OFF)

    with automatic_collection(True):
        result = pytester.runpytest("-p", "redsun.testing")
        after = gc.isenabled()

    result.assert_outcomes(passed=1)
    assert after


def test_a_modules_cycles_are_collected_when_it_ends(
    pytester: pytest.Pytester,
) -> None:
    """Collect the cycles a module left before the next module's tests run."""
    marker = str(pytester.path / "collected")
    pytester.makepyfile(
        test_first=LEAVES_A_CYCLE.format(marker=marker),
        test_second=FINDS_IT_FREED.format(marker=marker),
    )

    result = pytester.runpytest("-p", "redsun.testing")

    result.assert_outcomes(passed=2)


def test_a_test_leaving_collection_on_is_refused(pytester: pytest.Pytester) -> None:
    """Fail the test that left automatic collection on, and run the next with it off."""
    pytester.makepyfile(TURNS_COLLECTION_ON)

    result = pytester.runpytest("-p", "redsun.testing")

    result.assert_outcomes(passed=3, errors=1)
    result.stdout.fnmatch_lines(
        [
            "*left automatic garbage collection on*",
            "ERROR *::test_turns_collection_on*",
        ]
    )


@pytest.mark.parametrize(
    "disabled", [(), ("-p", "no:logging")], ids=["logging", "no-logging"]
)
def test_a_session_kept_alive_fails_its_test(
    pytester: pytest.Pytester, disabled: tuple[str, ...]
) -> None:
    """Fail a test whose session is still alive once it is over, with or without `pytest`'s logging plugin."""
    pytester.makepyfile(KEEPS_ITS_SESSION)

    result = pytester.runpytest_subprocess("-p", "redsun.testing", *disabled)

    result.assert_outcomes(passed=1, errors=1)
    result.stdout.fnmatch_lines(
        ["*RuntimeError: still alive after the test: 'kept' (Session); *"]
    )


@pytest.mark.parametrize(
    "source",
    [FIXTURE_RETURNS_IT, FAILS_TO_BUILD, LOGS_AT_SHUTDOWN],
    ids=["fixture", "failed-build", "shutdown-log"],
)
def test_a_session_only_pytest_held_passes(
    pytester: pytest.Pytester, source: str
) -> None:
    """Pass a test whose session only a fixture value or `pytest`'s log capture held."""
    pytester.makepyfile(source)

    result = pytester.runpytest_subprocess("-p", "redsun.testing")

    result.assert_outcomes(passed=1)


def test_a_test_that_raised_is_not_checked(pytester: pytest.Pytester) -> None:
    """Report only its own outcome for a test that raised after building a session."""
    pytester.makepyfile(RAISES)

    result = pytester.runpytest_subprocess("-p", "redsun.testing")

    result.assert_outcomes(failed=1, xfailed=1)
    result.stdout.no_fnmatch_line("*still alive after the test*")
