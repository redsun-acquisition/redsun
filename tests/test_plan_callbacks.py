"""A plan carries the callbacks it requires, and a user attaches the rest."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from mock_bundle.acquisition import MockAcquisitionPresenter
from mock_bundle.median import MockMedianPresenter
from mock_bundle.presenters import MockRegistrar
from mock_bundle.views import MockAcquisitionView

from redsun import AsPresenter, AsView, Session

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from redsun import Link
    from redsun.testing import BuildSession


class Plans(Session):
    config: ClassVar[dict[str, Any]] = {"session": "plan-callbacks"}

    acquisition: AsPresenter[MockAcquisitionPresenter]
    median: AsPresenter[MockMedianPresenter]
    registrar: AsPresenter[MockRegistrar]
    panel: AsView[MockAcquisitionView]

    def wire(self) -> Iterator[Link]:
        yield self.panel.sig_launch, self.acquisition.launch


class PlansWithoutAMedian(Session):
    config: ClassVar[dict[str, Any]] = {"session": "plan-callbacks-unfiltered"}

    acquisition: AsPresenter[MockAcquisitionPresenter]
    registrar: AsPresenter[MockRegistrar]
    panel: AsView[MockAcquisitionView]

    def wire(self) -> Iterator[Link]:
        yield self.panel.sig_launch, self.acquisition.launch


def test_a_plan_runs_with_the_callback_it_carries_first(
    config_home: Path, build: BuildSession
) -> None:
    """Run a plan with its own callback first, listed once, then the attached ones."""
    app = build(Plans)

    app.panel.request("median_scan")
    assert app.acquisition.run is not None
    app.acquisition.run.result(timeout=10)

    assert app.acquisition.subscribed == [app.median, app.registrar]
    assert app.median.documents == ["start", "stop"]
    assert app.registrar.documents == ["start", "stop"]


def test_a_plan_runs_with_the_arguments_and_callbacks_the_view_sends(
    config_home: Path, build: BuildSession
) -> None:
    """Run an open plan with the arguments and only the callbacks the view attaches."""
    app = build(Plans)
    app.panel.attach("stream", ["registrar"])

    app.panel.request("stream", {"frames": 3})
    assert app.acquisition.run is not None
    app.acquisition.run.result(timeout=10)

    assert app.acquisition.frames == 3
    assert app.acquisition.subscribed == [app.registrar]


def test_every_component_offering_plans_is_collected(
    config_home: Path, build: BuildSession
) -> None:
    """Collect the plans of every component offering them."""
    app = build(Plans)
    assert set(app.panel.specs) == {"stream", "median_scan"}
    assert set(app.acquisition.entries) == {"stream", "median_scan"}


def test_a_plan_is_absent_when_the_component_owning_it_is(
    config_home: Path, build: BuildSession
) -> None:
    """Leave out a plan whose owning component is not in the session."""
    app = build(PlansWithoutAMedian)
    assert set(app.panel.specs) == {"stream"}


def test_the_attached_callbacks_outlive_the_session(
    config_home: Path, build: BuildSession
) -> None:
    """Keep attached callbacks for the next session, dropping names no longer there."""
    first = build(Plans)
    assert first.panel.attached("stream") == ["median", "registrar"]
    first.panel.attach("stream", ["gone", "registrar"])

    second = build(Plans)
    assert second.panel.attached("stream") == ["registrar"]
