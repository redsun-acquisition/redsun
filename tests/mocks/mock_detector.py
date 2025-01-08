from __future__ import annotations

from typing import Any, ClassVar

from collections import OrderedDict

from sunflare.config import ModelInfo
from sunflare.engine import Status
from sunflare.model import ModelProtocol

from bluesky.protocols import Reading
from event_model.documents.event_descriptor import DataKey

from psygnal import SignalGroupDescriptor


class MockDetectorInfo(ModelInfo):
    """Mock motor model information."""

    integer: int
    floating: float
    string: str
    events: ClassVar[SignalGroupDescriptor] = SignalGroupDescriptor()

class MockDetector:
    def __init__(self, name: str, model_info: MockDetectorInfo) -> None:
        self.name = name
        self.model_info = model_info

    def stage(self) -> Status:
        raise NotImplementedError(
            "Mock detector model does not support stage operation."
        )

    def unstage(self) -> Status:
        raise NotImplementedError(
            "Mock detector model does not support unstage operation."
        )

    def read(self) -> OrderedDict[str, Reading[Any]]:
        raise NotImplementedError(
            "Mock detector model does not support read operation."
        )

    def shutdown(self) -> None:
        raise NotImplementedError(
            "Mock detector model does not support shutdown operation."
        )

    def pause(self) -> None:
        raise NotImplementedError(
            "Mock detector model does not support pause operation."
        )

    def resume(self) -> None:
        """Perform device-specific work when the RunEngine resumes after a pause."""
        raise NotImplementedError(
            "Mock detector model does not support resume operation."
        )

    def kickoff(self) -> Status:
        raise NotImplementedError(
            "Mock detector model does not support kickoff operation."
        )

    def complete(self) -> Status:
        raise NotImplementedError(
            "Mock detector model does not support complete operation."
        )

    def read_configuration(self) -> OrderedDict[str, Reading[Any]]:
        raise NotImplementedError(
            "Mock detector model does not support read_configuration operation."
        )

    def describe_configuration(self) -> OrderedDict[str, DataKey]:
        raise NotImplementedError(
            "Mock detector model does not support describe_configuration operation."
        )

    @property
    def integer(self) -> int:
        return self.model_info.integer

    @property
    def floating(self) -> float:
        return self.model_info.floating

    @property
    def string(self) -> str:
        return self.model_info.string


class OtherDetector(ModelProtocol):
    def __init__(self, name: str, model_info: MockDetectorInfo) -> None:
        super().__init__(name, model_info)

    def read(self) -> OrderedDict[str, Reading[Any]]:
        raise NotImplementedError("Mock detector model does not support read operation.")
    
    def stage(self) -> Status:
        raise NotImplementedError("Mock detector model does not support stage operation.")

    def unstage(self) -> Status:
        raise NotImplementedError("Mock detector model does not support unstage operation.")
    
    def read_configuration(self) -> OrderedDict[str, Reading[Any]]:
        raise NotImplementedError("Mock detector model does not support read_configuration operation.")

    def describe_configuration(self) -> OrderedDict[str, DataKey]:
        raise NotImplementedError("Mock detector model does not support describe_configuration operation.")
    
    def kickoff(self) -> Status:
        raise NotImplementedError("Mock detector model does not support kickoff operation.")
    
    def complete(self) -> Status:
        raise NotImplementedError("Mock detector model does not support complete operation.")
    
    def pause(self) -> None:
        raise NotImplementedError("Mock detector model does not support pause operation.")
    
    def resume(self) -> None:
        raise NotImplementedError("Mock detector model does not support resume operation.")

    def shutdown(self) -> None: ...

    @property
    def integer(self) -> int:
        return self.model_info.integer

    @property
    def floating(self) -> float:
        return self.model_info.floating

    @property
    def string(self) -> str:
        return self.model_info.string
