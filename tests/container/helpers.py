"""Shared helpers for container tests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mock_pkg.controller import SignalReader
    from mock_pkg.view import ReadingView

    from redsun.containers import AppContainer

C = TypeVar("C")


def component(mapping: Mapping[str, object], name: str, kind: type[C], /) -> C:
    """Fetch a component from a container mapping, checking its class.

    For containers built from a configuration file, where the components are
    named in the file rather than declared in code and the mapping is typed by
    the protocol they satisfy.

    Parameters
    ----------
    mapping : Mapping[str, object]
        A container's ``devices``, ``presenters`` or ``views``.
    name : str
        Key the component was registered under.
    kind : type[C]
        Class the component is expected to be.

    Returns
    -------
    C
        The component, narrowed to *kind*.
    """
    found = mapping[name]
    assert isinstance(found, kind), (
        f"{name!r} is a {type(found).__name__}, expected {kind.__name__}"
    )
    return found


def shut_down_after_a_read(
    app: AppContainer,
    panel: ReadingView,
    reader: SignalReader,
    caplog: pytest.LogCaptureFixture,
) -> tuple[list[tuple[str, object]], dict[str, object]]:
    """Read once through the panel, shut the session down, and check what is left.

    The panel is destroyed and nothing was logged at warning or above. What the
    panel showed and what the presenter read as it shut down are returned for
    the caller to compare.
    """
    readings = panel.readings
    panel.read_button.click()
    caplog.clear()

    app.shutdown()

    with pytest.raises(RuntimeError, match="deleted"):
        panel.isVisible()
    warnings: list[Any] = [
        r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert warnings == []
    return readings, reader.read_at_shutdown
