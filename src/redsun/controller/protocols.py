"""Module defining protocols for interacting with built-in controllers.

Models that want to be recognized by the built-in controllers
must implement the protocols defined in this module.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Optional, Protocol, Union, runtime_checkable

from sunflare.model import ModelProtocol

if TYPE_CHECKING:
    from bluesky.protocols import Location, Reading
    from event_model.documents.event_descriptor import DataKey
    from sunflare.engine import Status


@runtime_checkable
class MotorModel(Protocol, ModelProtocol):
    """Expected protocol for motor models.

    To be recognized as such, a ``MotorModel`` must implemement the methods listed below,
    together with the interface defined in :class:`~sunflare.model.ModelProtocol``.

    Exposes the following Bluesky protocols:

    - :meth:`~bluesky.protocols.Locatable` (``locate``)
    - :meth:`~bluesky.protocols.Settable` (``set``)
    """

    @abstractmethod
    def locate(self) -> Location[Union[int, float]]:
        """Get the current motor location.

        Returns
        -------
        ``Location[Union[int, float]]``
            Motor location.
        """
        ...

    @abstractmethod
    def set(self, value: Union[int, float], axis: Optional[str] = None) -> Status:
        """Set the motor location on a specific axis.

        Parameters
        ----------
        value : ``Union[int, float]``
            New motor location.
        axis : ``str``, optional
            Motor axis along which movement occurs, by default None.

        Returns
        -------
        Status
            Status object monitoring the operation.
        """

    @property
    @abstractmethod
    def axis(self) -> list[str]:
        """List of available motor axes."""
        ...

    @property
    @abstractmethod
    def step_size(self) -> dict[str, Union[int, float]]:
        """Dictionary of motor step sizes.

        Keys are the motor axes defined in the ``axis`` property.
        """
        ...

    @property
    @abstractmethod
    def egu(self) -> str:
        """Engineering unit.

        Represents the measurement unit of motor movements (e.g., mm, deg).
        """
        ...


@runtime_checkable
class DetectorModel(Protocol, ModelProtocol):
    """Expected protocol for detector models.

    To be recognized as such, a ``DetectorModel`` must implemement the methods listed below,
    together with the interface defined in :class:`~sunflare.model.ModelProtocol``.

    Exposes the following Bluesky protocols:

    - :meth:`~bluesky.protocols.Stageable` (``locate``)
    - :meth:`~bluesky.protocols.Readable` (``set``)
    """

    @abstractmethod
    def stage(self) -> Status:
        """Stage the detector for acquisition.

        The method implies a mechanism for the detector to start acquiring data.

        Returns
        -------
        Status
            Status object monitoring the operation.
        """
        ...

    @abstractmethod
    def unstage(self) -> Status:
        """Unstage the detector.

        The method implies a mechanism for the detector to stop acquiring data.
        It's the opposite of the ``stage`` method.

        Returns
        -------
        Status
            Status object monitoring the operation.
        """
        ...

    @abstractmethod
    def read(self) -> dict[str, Reading[Any]]:
        """Return a mapping of field names to the last value read.

        Example return value:

        .. code-block:: python

            OrderedDict(
                ("channel1", {"value": 5, "timestamp": 1472493713.271991}),
                ("channel2", {"value": 16, "timestamp": 1472493713.539238}),
            )

        Returns
        -------
        dict[str, Reading[Any]]
            Mapping of field names to the last value read.
        """
        ...

    @abstractmethod
    def describe(self) -> dict[str, DataKey]:
        """Return a dictionary with exactly the same keys as the ``read``.

        It provides a description of the data that will be returned by the ``read`` method.

        Example return value:

        .. code-block:: python

            OrderedDict(
                (
                    "channel1",
                    {"source": "XF23-ID:SOME_PV_NAME", "dtype": "number", "shape": []},
                ),
                (
                    "channel2",
                    {"source": "XF23-ID:SOME_PV_NAME", "dtype": "number", "shape": []},
                ),
            )
        """
        ...

    @property
    @abstractmethod
    def egu(self) -> str:
        """Engineering unit for exposure time."""
        ...
