"""Tests for the compute section and the compute class attribute."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest
from pydantic import ValidationError

from redsun import Session
from redsun._config import SessionFile
from redsun.compute import Budget
from redsun.errors import ConfigurationError

if TYPE_CHECKING:
    from redsun.testing import BuildSession


class LatencyApp(Session):
    compute = "latency"


class CappedApp(Session):
    compute: ClassVar[dict[str, object]] = {"preset": "throughput", "cores": 4}


@pytest.fixture(autouse=True)
def eight_physical_cores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the machine has eight physical cores."""
    monkeypatch.setattr("redsun.session._base.physical_cores", lambda: 8)


def test_a_bare_word_picks_the_preset() -> None:
    """Read `compute: latency` as the latency preset."""
    section = SessionFile.model_validate({"compute": "latency"}).compute
    assert section is not None
    assert section.preset == "latency"


def test_an_unknown_key_is_refused() -> None:
    """Refuse a key the compute section does not have."""
    with pytest.raises(ValidationError, match="extra"):
        SessionFile.model_validate({"compute": {"presets": "latency"}})


def test_the_class_sets_the_budget(build: BuildSession) -> None:
    """Take the preset from the class when the file has no compute section."""
    assert build(LatencyApp).compute_budget == Budget(
        cores=7, threads=1, native_threads=7
    )


def test_the_file_wins_over_the_class(build: BuildSession) -> None:
    """Take the session file's preset over the class attribute."""
    session = build(LatencyApp, {"compute": "throughput"})
    assert session.compute_budget == Budget(cores=7, threads=7, native_threads=1)


def test_the_file_overrides_key_by_key(build: BuildSession) -> None:
    """Keep the class's cap when the file sets only the preset."""
    session = build(CappedApp, {"compute": {"preset": "latency"}})
    assert session.compute_budget == Budget(cores=4, threads=1, native_threads=4)


def test_the_reserve_counts_its_cores(build: BuildSession) -> None:
    """Leave one core per reserve entry out of the budget."""
    session = build(
        Session, {"compute": {"preset": "throughput", "reserve": [0, 1, 2]}}
    )
    assert session.compute_budget.cores == 5


def test_the_budget_is_unavailable_before_build() -> None:
    """Refuse to read the budget before the session is built."""
    with pytest.raises(RuntimeError, match="build"):
        _ = Session().compute_budget


@pytest.mark.parametrize(
    "section",
    [{"switch_interval_ms": 0}, {"cores": 0}, {"reserve": [0, -1]}],
    ids=["switch-interval", "cores", "reserve"],
)
def test_a_value_out_of_range_is_refused(section: dict[str, object]) -> None:
    """Refuse a switch interval of zero, no cores and a negative reserved core."""
    with pytest.raises(ValidationError, match=next(iter(section))):
        SessionFile.model_validate({"compute": section})


@pytest.mark.parametrize("declared", ["fast", 5, {"cores": 0}])
def test_a_bad_class_value_is_refused(build: BuildSession, declared: object) -> None:
    """Refuse an unknown preset, a non-mapping or a bad setting declared by the class."""
    bad_app = type("BadApp", (Session,), {"compute": declared})
    with pytest.raises(ConfigurationError, match=r"BadApp\.compute"):
        build(bad_app)
