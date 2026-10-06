"""The built-in view switching and dimming lights."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from psygnal import Signal
from qtpy import QtWidgets as QtW

from redsun.log import Loggable
from redsun.ports import slot
from redsun.presenter import DescribesLights  # noqa: TC001
from redsun.qt import Dock
from redsun.view.qt.treeview import ConfigurationTab

from ..._settings import Settings  # noqa: TC001
from ._light_group import LightGroup

if TYPE_CHECKING:
    from redsun.view import Placement


class LightView(QtW.QWidget, Loggable):
    """Switch lights on and off and set their intensity: a group per light.

    The Lights tab holds one [`LightGroup`][redsun.view.qt.builtins.LightGroup]
    per light. The Configuration tab shows and edits every light's
    configuration. The Advanced tab chooses whether the intensity is also
    written while the slider is dragged; the choice is kept in the session's
    settings, under a key named after this view, and wins over the keyword.

    Parameters
    ----------
    write_while_dragging
        Write the intensity during a drag as well, at most every 100 ms,
        until the Advanced tab says otherwise.
    """

    placement: Placement = Dock("right")
    """Where the view sits in the main window."""

    group_class: ClassVar[type[LightGroup]] = LightGroup
    """Widget built for each light; a subclass may name a subclass of its own."""

    sig_enabled = Signal(str, bool)
    """Device, and the state asked for."""

    sig_intensity = Signal(str, float)
    """Device, and the intensity asked for."""

    sig_configure = Signal(str, object)
    """Key and value of an edit in the Configuration tab."""

    def __init__(
        self, name: str, parent: QtW.QWidget, *, write_while_dragging: bool = False
    ) -> None:
        super().__init__(parent)
        self.name = name
        self._groups: dict[str, LightGroup] = {}
        self._configuration_tab: ConfigurationTab | None = None
        self._settings: Settings | None = None
        self._dragging = QtW.QCheckBox("Write while dragging", self)
        self._dragging.setObjectName("write-while-dragging")
        self._dragging.setChecked(write_while_dragging)

        self._lights = QtW.QVBoxLayout()
        lights = QtW.QWidget(self)
        lights_layout = QtW.QVBoxLayout(lights)
        lights_layout.addLayout(self._lights)
        lights_layout.addStretch(1)
        scroll = QtW.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(lights)

        self._configuration = QtW.QVBoxLayout()
        configuration = QtW.QWidget(self)
        configuration.setLayout(self._configuration)

        advanced = QtW.QWidget(self)
        QtW.QVBoxLayout(advanced).addWidget(self._dragging)

        self._tabs = QtW.QTabWidget(self)
        self._tabs.addTab(scroll, "Lights")
        self._tabs.addTab(configuration, "Configuration")
        self._tabs.addTab(advanced, "Advanced")
        QtW.QVBoxLayout(self).addWidget(self._tabs)

    @property
    def tabs(self) -> QtW.QTabWidget:
        """The Lights, Configuration and Advanced tabs, to which a subclass may add."""
        return self._tabs

    def setup(self, lights: DescribesLights, settings: Settings) -> None:
        """Build a group per light *lights* describes, and read *settings*."""
        self._settings = settings
        stored = settings.get(self._key("write_while_dragging"))
        if isinstance(stored, bool):
            self._dragging.setChecked(stored)
        for device, info in lights.lights.items():
            group = self.group_class(
                device,
                info,
                write_while_dragging=self._dragging.isChecked(),
                parent=self,
            )
            group.sig_enabled.connect(self.sig_enabled.emit)
            group.sig_intensity.connect(self.sig_intensity.emit)
            self._groups[device] = group
            self._lights.addWidget(group)
        self._configuration_tab = ConfigurationTab(lights.configuration, self)
        self._configuration_tab.sig_configure.connect(self.sig_configure.emit)
        self._configuration.addWidget(self._configuration_tab)
        self._dragging.toggled.connect(self._set_dragging)

    @slot(signal="sig_enabled")
    def update_enabled(self, device: str, on: bool) -> None:
        """Show whether *device* is on."""
        self._groups[device].set_enabled(on)

    @slot(signal="sig_intensity")
    def update_intensity(self, device: str, value: float) -> None:
        """Show the intensity *device* reads back."""
        self._groups[device].set_intensity(value)

    @slot(signal="sig_failed")
    def set_failed(self, device: str, message: str) -> None:
        """Show that the last write to *device* failed with *message*."""
        self._groups[device].set_failed(message)

    @slot(signal="sig_configuration")
    def update_configuration(self, key: str, value: object) -> None:
        """Show *value*, read back from the configuration signal *key*."""
        if self._configuration_tab is not None:
            self._configuration_tab.update_value(key, value)

    @slot(signal="sig_locks_changed")
    def set_locked(self, names: frozenset[str]) -> None:
        """Disable the controls of the lights in *names*, and enable the rest."""
        for device, group in self._groups.items():
            group.set_locked(device in names)
        if self._configuration_tab is not None:
            self._configuration_tab.set_locked(names)

    def _key(self, setting: str) -> str:
        return f"{self.name}.{setting}"

    def _set_dragging(self, on: bool) -> None:
        for group in self._groups.values():
            group.set_write_while_dragging(on)
        if self._settings is not None:
            self._settings.set(self._key("write_while_dragging"), on)
