"""A session showing its records in the built-in log view."""

from __future__ import annotations

from typing import Any, ClassVar

from redsun import AsView  # noqa: TC001
from redsun.qt import QtSession
from redsun.view.qt.builtins import LogView  # noqa: TC001


# --8<-- [start:session]
class MyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "my-lab"}

    logs: AsView[LogView]


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
