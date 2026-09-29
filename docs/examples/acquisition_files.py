"""The session of the guide "How to choose where acquisition files go"."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Any, ClassVar

import bluesky.plans as bp
from ophyd_async.core import PathProvider, StandardReadable
from psygnal import Signal
from qtpy.QtWidgets import QFileDialog, QPushButton, QVBoxLayout, QWidget

from redsun import (
    AsDevice,
    AsPresenter,
    AsView,
    DeviceMapping,
    Link,
    Placement,
    slot,
)
from redsun.engine import RunEngine
from redsun.path_provider import SessionPathProvider  # noqa: TC001
from redsun.qt import Dock, QtSession


# --8<-- [start:device]
class MyCamera(StandardReadable):
    def __init__(self, path_provider: PathProvider, name: str = "") -> None:
        self.path_provider = path_provider
        super().__init__(name=name)


# --8<-- [end:device]
# --8<-- [start:controller]
class MyController:
    sig_started = Signal(str)
    sig_finished = Signal()

    def __init__(
        self, name: str, *, devices: DeviceMapping, paths: SessionPathProvider
    ) -> None:
        self.name = name
        self.devices = devices
        self.paths = paths
        self.engine = RunEngine()

    @slot
    def snap(self) -> None:
        camera = self.devices["camera"]
        assert isinstance(camera, MyCamera)
        self.sig_started.emit("snap")
        future = self.engine(bp.count([camera]))
        future.add_done_callback(lambda _: self.sig_finished.emit())


# --8<-- [end:controller]
# --8<-- [start:view]
class FolderView(QWidget):
    placement: Placement = Dock("left")
    sig_snap = Signal()
    sig_directory_chosen = Signal(str)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        snap = QPushButton("Snap")
        snap.clicked.connect(lambda: self.sig_snap.emit())
        choose = QPushButton("Choose folder")
        choose.clicked.connect(self.choose_folder)
        layout = QVBoxLayout(self)
        layout.addWidget(snap)
        layout.addWidget(choose)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder for the files")
        if folder:
            self.sig_directory_chosen.emit(folder)


# --8<-- [end:view]
# --8<-- [start:session]
class MyApp(QtSession):
    # --8<-- [start:config]
    config: ClassVar[dict[str, Any]] = {
        "session": "my-lab",
        "storage": {"base_dir": "~/experiments"},
    }
    # --8<-- [end:config]
    camera: AsDevice[MyCamera]
    ctrl: AsPresenter[MyController]
    folder_view: AsView[FolderView]

    def wire(self) -> Iterator[Link]:
        yield self.folder_view.sig_snap, self.ctrl.snap
        # --8<-- [start:wire-plan]
        yield self.ctrl.sig_started, self.path_provider.set_plan
        yield self.ctrl.sig_finished, self.path_provider.reset_plan
        # --8<-- [end:wire-plan]
        # --8<-- [start:wire-folder]
        yield self.folder_view.sig_directory_chosen, self.path_provider.set_base_dir
        # --8<-- [end:wire-folder]


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
