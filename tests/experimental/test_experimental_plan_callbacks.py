"""A plan carries the callbacks it requires, and a user attaches the rest."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from mock_bundle.acquisition import MockAcquisitionPresenter
from mock_bundle.median import MockMedianPresenter
from mock_bundle.presenters import MockRegistrar
from mock_bundle.views import MockAcquisitionView

from redsun.experimental import AsPresenter, AsView, Session

if TYPE_CHECKING:
    from pathlib import Path

    from .conftest import BuildSession


class Plans(Session):
    config: ClassVar[dict[str, Any]] = {"name": "plan-callbacks"}

    acquisition: AsPresenter[MockAcquisitionPresenter]
    median: AsPresenter[MockMedianPresenter]
    registrar: AsPresenter[MockRegistrar]
    panel: AsView[MockAcquisitionView]

    def wire(self) -> None:
        self.connect(self.panel.sig_launch, self.acquisition.launch)


class PlansWithoutAMedian(Session):
    config: ClassVar[dict[str, Any]] = {"name": "plan-callbacks-unfiltered"}

    acquisition: AsPresenter[MockAcquisitionPresenter]
    registrar: AsPresenter[MockRegistrar]
    panel: AsView[MockAcquisitionView]

    def wire(self) -> None:
        self.connect(self.panel.sig_launch, self.acquisition.launch)


def test_a_plan_runs_with_the_callback_it_carries_first(
    config_home: Path, build: BuildSession
) -> None:
    """The median presenter owns the plan and is its callback, listed once."""
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
    """An open plan carries none of its own, so only the attached ones run."""
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
    app = build(Plans)
    assert set(app.panel.specs) == {"stream", "median_scan"}
    assert set(app.acquisition.entries) == {"stream", "median_scan"}


def test_a_plan_is_absent_when_the_component_owning_it_is(
    config_home: Path, build: BuildSession
) -> None:
    app = build(PlansWithoutAMedian)
    assert set(app.panel.specs) == {"stream"}


def test_the_attached_callbacks_outlive_the_session(
    config_home: Path, build: BuildSession
) -> None:
    """A name no longer in the catalogue is dropped rather than refused."""
    first = build(Plans)
    assert first.panel.attached("stream") == ["median", "registrar"]
    first.panel.attach("stream", ["gone", "registrar"])

    second = build(Plans)
    assert second.panel.attached("stream") == ["registrar"]
