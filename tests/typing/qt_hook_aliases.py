"""Type-level assertions for the Qt hook protocol aliases.

Never imported or executed: a type checker verifies these declarations.
The point of parameterising the hook protocols on the toolkit object is that a
provider written against the wrong one fails statically, which no runtime check
can see - `isinstance` cannot be given a parameterised protocol, so the
container narrows to the bare form and a mismatch only surfaces when called.

Checked by the project's normal mypy invocation; see CLAUDE.md.
"""

from __future__ import annotations

from typing import assert_type

from qtpy.QtWidgets import QApplication, QMainWindow, QWidget

from redsun.qt import (
    QtConfiguresApplication,
    QtConfiguresMainView,
    QtCreatesApplication,
)


class StyleProvider:
    """Satisfies every Qt hook point."""

    def create_application(self, argv: list[str]) -> QApplication:
        return QApplication(argv)

    def configure_application(self, app: QApplication) -> None: ...

    def configure_main_view(self, view: QMainWindow) -> None: ...


class WrongToolkit:
    """Takes an unrelated object at each moment.

    Note the parameters must be *unrelated*, not merely wider: a hook point
    parameter is contravariant, so a `configure_main_view` accepting `QWidget`
    legitimately satisfies one demanding `QMainWindow`, which is a `QWidget`.
    """

    def create_application(self, argv: list[str]) -> QWidget:  # type: ignore[empty-body]
        ...

    def configure_application(self, app: QWidget) -> None: ...

    def configure_main_view(self, view: QApplication) -> None: ...


def takes_creates(_: QtCreatesApplication) -> None: ...
def takes_configures(_: QtConfiguresApplication) -> None: ...
def takes_window(_: QtConfiguresMainView) -> None: ...


def check_a_qt_provider_satisfies_the_aliases(provider: StyleProvider) -> None:
    takes_creates(provider)
    takes_configures(provider)
    takes_window(provider)

    assert_type(provider.create_application([]), QApplication)


def check_the_wrong_toolkit_is_refused(provider: WrongToolkit) -> None:
    takes_creates(provider)  # type: ignore[arg-type]
    takes_configures(provider)  # type: ignore[arg-type]
    takes_window(provider)  # type: ignore[arg-type]
