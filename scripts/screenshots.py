"""Run the documentation's example sessions and save a picture of each window.

``QApplication.exec`` is replaced by a function that photographs the main
window, so a script calling ``run()`` stops there instead of starting the event
loop. Settings and log files go to a temporary folder, so a layout saved on this
machine does not change the picture. Run from the repository root.

Each script runs in a process of its own, as a session does when a user starts
it: a second Qt application in one process finds the timer ``psygnal`` made for
the first, which was deleted with it.

The window opens on the platform's own display, which has the fonts the text
needs; CI provides one with a virtual display.
"""

from __future__ import annotations

import runpy
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

from qtpy.QtCore import QLocale
from qtpy.QtWidgets import QApplication, QDockWidget, QMainWindow, QPushButton

SCREENSHOTS: dict[Path, tuple[Path, tuple[int, int], str | None]] = {
    Path("docs/tutorials/first_session.py"): (
        Path("docs/tutorials/images/first-session.png"),
        (420, 220),
        None,
    ),
    Path("docs/tutorials/device_protocols.py"): (
        Path("docs/tutorials/images/device-protocols.png"),
        (420, 300),
        None,
    ),
    Path("docs/tutorials/plan_form.py"): (
        Path("docs/tutorials/images/plan-form.png"),
        (820, 340),
        None,
    ),
    Path("docs/tutorials/acquire_images.py"): (
        Path("docs/tutorials/images/acquire-images.png"),
        (820, 760),
        "camera_view",
    ),
}
"""Each example script, with where its picture is written, the size of the
window, and the view whose **Run** is pressed before the picture, if any."""

SETTLE = 3.0
"""Seconds a plan started for a picture is given to finish."""


def photograph(target: Path, size: tuple[int, int], press: str | None) -> int:
    """Save the visible main window to *target*, and close every window."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    window = next(
        w for w in app.topLevelWidgets() if isinstance(w, QMainWindow) and w.isVisible()
    )
    window.resize(*size)
    if press is not None:
        view = next(
            d for d in window.findChildren(QDockWidget) if d.windowTitle() == press
        )
        next(b for b in view.findChildren(QPushButton) if b.text() == "Run").click()
        finished = time.monotonic() + SETTLE
        while time.monotonic() < finished:
            app.processEvents()
            time.sleep(0.05)
    # let queued signals and the layout settle before the picture is taken
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    target.parent.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(target))
    # what quitting the event loop sends, and what shuts the session down
    app.aboutToQuit.emit()
    return 0


def capture(
    script: Path, target: Path, size: tuple[int, int], press: str | None
) -> None:
    """Run *script* as ``__main__`` and photograph the window it shows."""
    with tempfile.TemporaryDirectory() as home:

        def elsewhere(*_: object, **__: object) -> str:
            return home

        # numbers are written the same way whatever machine takes the picture
        QLocale.setDefault(QLocale(QLocale.Language.English))
        with (
            mock.patch("redsun._settings.user_config_dir", elsewhere),
            mock.patch("redsun.log.user_data_dir", elsewhere),
            mock.patch("redsun.path_provider.user_data_dir", elsewhere),
            mock.patch.object(
                QApplication, "exec", lambda _: photograph(target, size, press)
            ),
        ):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit:
                pass
    print(f"wrote {target}")


def main(arguments: list[str]) -> None:
    """Photograph the script named in *arguments*, or each script in a process."""
    if arguments:
        script = Path(arguments[0])
        capture(script, *SCREENSHOTS[script])
        return
    for script in SCREENSHOTS:
        subprocess.run([sys.executable, __file__, script.as_posix()], check=True)


if __name__ == "__main__":
    main(sys.argv[1:])
