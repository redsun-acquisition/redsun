"""Tests for reading the annotations of a component's constructor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from redsun import AsDevice, AsPresenter, Session
from tests.sdk.mocks import Stage
from tests.shadowed_positioner import ShadowedPositioner

if TYPE_CHECKING:
    import pytest

    from redsun.registry import DeviceMapping as HiddenMapping
    from redsun.testing import BuildSession


class Hidden:
    """A presenter asking for a type its module imports only for type checking."""

    def __init__(self, name: str, *, devices: HiddenMapping) -> None:
        self.name = name


class ShadowedLab(Session):
    config: ClassVar[dict[str, Any]] = {"session": "shadowed-lab"}

    stage: AsDevice[Stage]
    positioner: AsPresenter[ShadowedPositioner]


class HiddenLab(Session):
    config: ClassVar[dict[str, Any]] = {"session": "hidden-lab"}

    hidden: AsPresenter[Hidden]


def test_an_inherited_field_resolves_in_the_module_declaring_it(
    build: BuildSession,
) -> None:
    """Inject an inherited field by its type, not by a same-named one of the subclass."""
    session = build(ShadowedLab)

    assert set(session.positioner.axes) == {"stage"}


def test_a_type_imported_only_for_type_checking_is_reported(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip a component whose annotation names a type absent at runtime, and say which."""
    session = build(HiddenLab)

    assert dict(session.presenters) == {}
    assert "'HiddenMapping' is not available at runtime" in caplog.text
