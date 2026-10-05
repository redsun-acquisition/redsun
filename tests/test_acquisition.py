"""Tests for the acquisition built-ins in a session."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from redsun import AsPresenter, Link, Session
from redsun.engine import Deferrals, RunEngine
from redsun.presenter import AcquisitionPresenter

if TYPE_CHECKING:
    from pathlib import Path

    from redsun.testing import BuildSession


class Follower:
    """A presenter that asks for the engine and its deferrals."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.engine: RunEngine | None = None
        self.deferrals: Deferrals | None = None

    def setup(self, engine: RunEngine, deferrals: Deferrals) -> None:
        """Keep what the session shares."""
        self.engine = engine
        self.deferrals = deferrals


class Lab(Session):
    config: ClassVar[dict[str, Any]] = {"session": "acquisition-lab"}

    acquisition: AsPresenter[AcquisitionPresenter]
    follower: AsPresenter[Follower]

    def wire(self) -> Iterator[Link]:
        yield from ()


class TwoRunners(Session):
    config: ClassVar[dict[str, Any]] = {"session": "acquisition-twice"}

    first: AsPresenter[AcquisitionPresenter]
    second: AsPresenter[AcquisitionPresenter]


def test_the_engine_and_deferrals_reach_a_component_that_asks(
    config_home: Path, build: BuildSession
) -> None:
    """Give a component asking for a `RunEngine` and `Deferrals` the presenter's own."""
    session = build(Lab)

    assert session.follower.engine is session.acquisition.engine()
    assert session.follower.deferrals is session.acquisition.deferrals()


def test_a_session_with_two_acquisition_presenters_is_refused(
    config_home: Path,
) -> None:
    """Refuse a session in which two acquisition presenters share an engine."""
    with pytest.raises(TypeError, match="share"):
        TwoRunners().build()
