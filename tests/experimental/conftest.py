from __future__ import annotations

import contextlib
import sys
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar
from unittest import mock

import pytest

from redsun._config import Source
from redsun.experimental import Session

_TESTS_DIR = str(Path(__file__).parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

_MOCK_PKG_DIR = Path(__file__).parent / "mock_bundle"

if TYPE_CHECKING:
    from collections.abc import Generator

SessionT = TypeVar("SessionT", bound=Session)


class BuildSession(Protocol):
    """Build a session, and hand it back typed as what was asked for."""

    def __call__(
        self, container: type[SessionT] | SessionT, config: Source | None = ..., /
    ) -> SessionT: ...


@pytest.fixture
def config_path() -> Path:
    """Return the directory holding the test session configurations."""
    return Path(__file__).parent / "configs"


@pytest.fixture
def build() -> Generator[BuildSession, None, None]:
    """Return a function building a session and shutting it down afterwards.

    Parameters
    ----------
    container : type[SessionT] | SessionT
        A container class, or a container already in hand.
    config : Source | None
        Laid over what the class declares, for a container built here.

    Every session it built is shut down in reverse order once the test ends,
    and a test may shut one down itself, ``shutdown`` running nothing the
    second time.
    """
    built: list[Session] = []

    def build_one(
        container: type[SessionT] | SessionT, config: Source | None = None, /
    ) -> SessionT:
        unbuilt = container(config) if isinstance(container, type) else container
        session = unbuilt.build()
        built.append(session)
        return session

    yield build_one
    for session in reversed(built):
        session.shutdown()


@pytest.fixture
def config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the settings store at *tmp_path*, off the user's own directory."""
    monkeypatch.setattr(
        "redsun.experimental._settings.user_config_dir", lambda *a, **k: str(tmp_path)
    )
    return tmp_path


@pytest.fixture
def mock_plugin() -> Generator[None, None, None]:
    """Present ``mock_bundle`` as an installed ``redsun.plugins`` entry point.

    The loader resolves a manifest through ``entry_points`` and
    ``importlib.resources``; both are redirected at the on-disk package so
    that discovery runs for real rather than being stubbed out.
    """
    entry = mock.Mock(spec=EntryPoint)
    entry.name = "mock-bundle"
    entry.value = "redsun.yaml"
    entry.group = "redsun.plugins"

    @contextlib.contextmanager
    def as_file(path: str | Path) -> Generator[Path, None, None]:
        yield path if isinstance(path, Path) else Path(path)

    with (
        mock.patch(
            "redsun.experimental.session._plugins.entry_points", return_value=[entry]
        ),
        mock.patch(
            "redsun.experimental.session._plugins.files",
            side_effect=lambda _: _MOCK_PKG_DIR,
        ),
        mock.patch("redsun.experimental.session._plugins.as_file", side_effect=as_file),
    ):
        yield
