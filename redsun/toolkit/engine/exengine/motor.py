"""ExEngine motor model available for creating custom device interfaces with the RedSun Toolkit."""

from exengine.backends.micromanager import (
    MicroManagerSingleAxisStage as ExEngineMMSingleMotor,
)
from exengine.backends.micromanager import MicroManagerXYStage as ExEngineMMDoubleMotor
from exengine.device_types import (
    TriggerableDoubleAxisPositioner as ExEngineDoubleMotor,
)
from exengine.device_types import (
    TriggerableSingleAxisPositioner as ExEngineSingleMotor,
)

from redsun.toolkit.config import MotorModelInfo
from redsun.toolkit.engine.motor import MotorModel


class ExEngineSingleMotorModel(MotorModel, ExEngineSingleMotor):  # type: ignore[misc]  # noqa: D101
    def __init__(self, name: str, model_info: MotorModelInfo):
        MotorModel.__init__(self, name, model_info)

        # TODO: investigate this initializer
        ExEngineSingleMotor.__init__(
            self, name, no_executor=False, no_executor_attrs=("_name",)
        )


class ExEngineDoubleMotorModel(MotorModel, ExEngineDoubleMotor):  # type: ignore[misc]  # noqa: D101
    def __init__(self, name: str, model_info: MotorModelInfo):
        MotorModel.__init__(self, name, model_info)

        # TODO: investigate this initializer
        ExEngineDoubleMotor.__init__(
            self, name, no_executor=False, no_executor_attrs=("_name",)
        )


class ExEngineMMSingleMotorModel(MotorModel, ExEngineMMSingleMotor):  # type: ignore[misc]  # noqa: D101
    def __init__(self, name: str, model_info: MotorModelInfo):
        MotorModel.__init__(self, name, model_info)
        ExEngineMMSingleMotor.__init__(self, name)


class ExEngineMMDoubleMotorModel(MotorModel, ExEngineMMDoubleMotor):  # type: ignore[misc]  # noqa: D101
    def __init__(self, name: str, model_info: MotorModelInfo):
        MotorModel.__init__(self, name, model_info)
        ExEngineMMDoubleMotor.__init__(self, name)
