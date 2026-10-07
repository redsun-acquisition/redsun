"""Tests for the acquisition presenter."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Annotated, Any

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import pytest
from annotated_types import Ge
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator

from redsun.aio import get_shared_loop
from redsun.engine.actions import ActionManager
from redsun.path_provider import SessionPathProvider
from redsun.presenter import AcquisitionPresenter
from tests.sdk.mocks import MockDetector, QuietAxis

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping
    from pathlib import Path

    from redsun import PlanEntry


class RecordedActions(ActionManager):
    """An action manager that records the requests it receives."""

    def __init__(self) -> None:
        super().__init__()
        self.requested: list[tuple[str, bool]] = []

    def request(self, name: str, on: bool = True) -> None:
        """Record the request."""
        self.requested.append((name, on))


class Plans:
    """Offers plans that rest, fail, hold the engine and read a device."""

    def __init__(self, name: str = "plans") -> None:
        self.name = name
        self.actions = RecordedActions()
        self.running = threading.Event()
        self.cleaned = threading.Event()

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Return the plans offered."""
        return {
            "rest": {"plan": self.rest},
            "broken": {"plan": self.broken},
            "hold": {"plan": self.hold},
            "pausable": {"plan": self.pausable},
            "read": {"plan": self.read},
            "guarded": {"plan": self.guarded},
            "limited": {"plan": self.limited},
        }

    def limited(self, frames: Annotated[int, Ge(1)] = 1) -> MsgGenerator[None]:
        """End at once, taking a frame count of at least one."""
        yield from ()

    def rest(self) -> MsgGenerator[None]:
        """End at once."""
        yield from bps.null()

    def broken(self) -> MsgGenerator[None]:
        """Raise after one message."""
        yield from bps.null()
        raise ValueError("bad target")

    def hold(self) -> MsgGenerator[None]:
        """Keep the engine busy until stopped, saying when it has begun."""
        self.running.set()
        yield from bps.sleep(30)

    def pausable(self) -> MsgGenerator[None]:
        """Keep the engine busy, with a checkpoint to pause at, until stopped."""
        self.running.set()
        while True:
            yield from bps.checkpoint()
            yield from bps.sleep(0.01)

    def read(self, device: Readable[Any]) -> MsgGenerator[None]:
        """Read one device."""
        yield from bps.rd(device)

    def guarded(self) -> MsgGenerator[None]:
        """Hold the engine until stopped, then take time to clean up."""
        self.running.set()
        yield from bpp.finalize_wrapper(bps.sleep(30), self.clean_up())

    def clean_up(self) -> MsgGenerator[None]:
        """Take half a second, then say the cleanup is done."""
        yield from bps.sleep(0.5)
        self.cleaned.set()


class Thing:
    """A type no plan widget can show."""


class Unreadable:
    """Offers a plan whose signature no widget can show."""

    name = "unreadable"

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Return the plan offered."""
        return {"odd": {"plan": self.odd}, "flat": {"plan": self.flat}}

    def odd(self, thing: Thing) -> MsgGenerator[None]:
        """Take an argument of a type no widget shows."""
        yield from bps.null()

    def flat(self) -> MsgGenerator[None]:
        """Return a plan instead of being a generator function."""
        return self.odd(Thing())


class RecordedPaths(SessionPathProvider):
    """A path provider that records the plan names it is given."""

    def __init__(self, base_dir: Path) -> None:
        super().__init__(base_dir=base_dir, session="s")
        self.names: list[str | None] = []

    def set_plan(self, plan: str) -> None:
        """Record *plan*."""
        self.names.append(plan)
        super().set_plan(plan)

    def reset_plan(self) -> None:
        """Record the reset."""
        self.names.append(None)
        super().reset_plan()


@pytest.fixture
def plans() -> Plans:
    """Return the plans the presenter is given."""
    return Plans()


@pytest.fixture
def paths(tmp_path: Path) -> RecordedPaths:
    """Return the path provider recording what the presenter asks for."""
    return RecordedPaths(tmp_path)


@pytest.fixture
def presenter(
    plans: Plans, paths: RecordedPaths, detector: MockDetector
) -> Generator[AcquisitionPresenter, None, None]:
    """Return an acquisition presenter set up with the plans and paths, shut down afterwards."""
    acquisition = AcquisitionPresenter(
        "acquisition", devices={"det1": detector, "plain": QuietAxis("plain")}
    )
    acquisition.setup({"plans": plans, "unreadable": Unreadable()}, {}, paths)
    yield acquisition
    acquisition.shutdown()


def record(
    presenter: AcquisitionPresenter,
) -> tuple[list[tuple[Any, ...]], threading.Event]:
    """Record every end signal of *presenter*, and return an event set on the first."""
    seen: list[tuple[Any, ...]] = []
    ended = threading.Event()

    def note(kind: str) -> Any:
        def receive(*args: Any) -> None:
            seen.append((kind, *args))
            if kind != "started":
                ended.set()

        return receive

    presenter.sig_plan_started.connect(note("started"))
    presenter.sig_plan_done.connect(note("done"))
    presenter.sig_plan_failed.connect(note("failed"))
    return seen, ended


def test_a_plan_runs_to_its_end_and_names_its_files(
    presenter: AcquisitionPresenter, paths: RecordedPaths
) -> None:
    """Report a plan started then done, with its files named after it meanwhile."""
    seen, ended = record(presenter)

    presenter.launch("rest", {})

    assert ended.wait(10)
    assert seen == [("started", "rest"), ("done", "rest")]
    assert paths.names == ["rest", None]


def test_a_plan_that_raises_is_reported_failed(
    presenter: AcquisitionPresenter, caplog: pytest.LogCaptureFixture
) -> None:
    """Report and log a plan that raises, with its message."""
    seen, ended = record(presenter)

    presenter.launch("broken", {})

    assert ended.wait(10)
    assert seen == [("started", "broken"), ("failed", "broken", "bad target")]
    assert "'broken' failed" in caplog.text


@pytest.mark.parametrize("value", ["ghost", "plain", 3])
def test_values_the_plan_cannot_take_are_reported_and_not_run(
    presenter: AcquisitionPresenter, value: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Fail, with a warning and no traceback, a launch naming no device, a device of the wrong kind, or no name."""
    seen, ended = record(presenter)

    presenter.launch("read", {"device": value})

    assert ended.wait(10)
    assert [kind for kind, *_ in seen] == ["failed"]
    assert [r.exc_info for r in caplog.records if r.levelname != "DEBUG"] == [None]


def test_a_value_outside_its_limits_is_refused_before_launch(
    presenter: AcquisitionPresenter,
) -> None:
    """Report a plan failed with the broken limit, and start nothing."""
    seen, _ = record(presenter)

    presenter.launch("limited", {"frames": 0})

    assert seen == [
        ("failed", "limited", "frames: Input should be greater than or equal to 1")
    ]


def test_a_launch_while_a_plan_runs_is_refused(
    presenter: AcquisitionPresenter, plans: Plans, caplog: pytest.LogCaptureFixture
) -> None:
    """Start nothing while another plan runs, and stop the first as done."""
    seen, ended = record(presenter)

    presenter.launch("hold", {})
    presenter.launch("rest", {})
    assert plans.running.wait(10)
    presenter.stop()

    assert ended.wait(10)
    assert seen == [("started", "hold"), ("done", "hold")]
    assert "not launched" in caplog.text


def test_a_stop_right_after_launch_stops_the_plan(
    presenter: AcquisitionPresenter,
) -> None:
    """Stop a plan asked to stop before the engine has started it."""
    seen, ended = record(presenter)
    loop_free = threading.Event()
    # the engine enters its running state on the shared loop, so a held
    # loop keeps the plan launched but not started
    get_shared_loop().call_soon_threadsafe(loop_free.wait, 10)
    try:
        presenter.launch("hold", {})
        presenter.stop()
    finally:
        loop_free.set()

    assert ended.wait(10)
    assert seen == [("started", "hold"), ("done", "hold")]


def test_pause_resume_and_stop_with_no_plan_running_are_ignored(
    presenter: AcquisitionPresenter,
) -> None:
    """Ignore pause, resume and stop once the plan has ended."""
    seen, ended = record(presenter)
    presenter.launch("rest", {})
    assert ended.wait(10)

    presenter.pause()
    presenter.resume()
    presenter.stop()

    assert seen == [("started", "rest"), ("done", "rest")]


def test_a_paused_plan_reports_nothing_until_it_is_stopped(
    presenter: AcquisitionPresenter,
    plans: Plans,
    wait_until: Callable[..., bool],
) -> None:
    """Report no end on a pause, and a single done once the paused plan is stopped."""
    seen, ended = record(presenter)
    presenter.launch("pausable", {})
    assert plans.running.wait(10)

    presenter.pause()
    assert wait_until(lambda: presenter.engine().state == "paused", timeout=10)
    reported_while_paused = ended.is_set()
    presenter.stop()

    assert ended.wait(10)
    assert not reported_while_paused
    assert seen == [("started", "pausable"), ("done", "pausable")]


def test_a_plan_no_widget_can_show_is_left_out(
    presenter: AcquisitionPresenter, caplog: pytest.LogCaptureFixture
) -> None:
    """Offer every readable plan and leave out, with a warning, each one that cannot be read."""
    warnings = " ".join(r.getMessage() for r in caplog.get_records("setup"))

    assert set(presenter.plans) == {
        "rest",
        "broken",
        "hold",
        "pausable",
        "read",
        "guarded",
        "limited",
    }
    assert ("'odd'" in warnings, "'flat'" in warnings) == (True, True)


def test_actions_are_relayed_and_requests_reach_the_running_plan(
    presenter: AcquisitionPresenter, plans: Plans
) -> None:
    """Relay a provider's action states, and send a request to the running plan's provider."""
    changes: list[tuple[str, object]] = []
    presenter.sig_action_changed.connect(lambda *args: changes.append(args))
    _, ended = record(presenter)

    plans.actions.sig_changed.emit("go", "offered")
    presenter.launch("hold", {})
    assert plans.running.wait(10)
    presenter.request_action("go", True)
    presenter.stop()

    assert ended.wait(10)
    assert changes == [("go", "offered")]
    assert plans.actions.requested == [("go", True)]


def test_an_action_with_no_plan_running_is_refused(
    presenter: AcquisitionPresenter, plans: Plans, caplog: pytest.LogCaptureFixture
) -> None:
    """Refuse an action request while no plan runs."""
    presenter.request_action("go", True)

    assert plans.actions.requested == []
    assert "refused" in caplog.text


def test_a_refused_base_directory_is_logged(
    presenter: AcquisitionPresenter,
    paths: RecordedPaths,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a base directory the path provider refuses, and report a new one."""
    changes: list[object] = []
    presenter.sig_base_dir_changed.connect(changes.append)
    accepted = tmp_path / "data"

    presenter.set_base_dir(accepted)
    paths.lock_base_dir("a plan is writing")
    presenter.set_base_dir(tmp_path / "elsewhere")

    assert changes == [accepted]
    assert presenter.base_dir == accepted
    assert "base directory" in caplog.text


def test_shutdown_aborts_a_running_plan_after_its_cleanup_without_a_report(
    plans: Plans, paths: RecordedPaths
) -> None:
    """Return from shutdown once the aborted plan has cleaned up, reporting no end."""
    presenter = AcquisitionPresenter("acquisition", devices={})
    presenter.setup({"plans": plans}, {}, paths)
    seen, ended = record(presenter)
    presenter.launch("guarded", {})
    assert plans.running.wait(10)

    presenter.shutdown()
    cleaned = plans.cleaned.is_set()
    # the future's callbacks may run just after the wait in shutdown returns
    reported = ended.wait(0.1)

    assert cleaned
    assert not reported
    assert [kind for kind, *_ in seen] == ["started"]


def test_resuming_before_the_pause_is_reached_withdraws_it(
    presenter: AcquisitionPresenter,
    plans: Plans,
    wait_until: Callable[..., bool],
) -> None:
    """Withdraw a pause no checkpoint has reached, and report the plan done when stopped."""
    seen, ended = record(presenter)
    presenter.launch("hold", {})
    assert plans.running.wait(10)

    presenter.pause()
    presenter.resume()
    withdrawn = wait_until(
        lambda: not presenter.engine().deferred_pause_requested, timeout=5
    )
    presenter.stop()

    assert ended.wait(10)
    assert withdrawn
    assert seen == [("started", "hold"), ("done", "hold")]
