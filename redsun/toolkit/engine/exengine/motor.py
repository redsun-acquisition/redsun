from redsun.toolkit.config import MotorModelInfo
from redsun.toolkit.engine.motor import MotorModel
from exengine.device_types import (
    TriggerableSingleAxisPositioner as ExEngineSingleMotor,
    TriggerableDoubleAxisPositioner as ExEngineDoubleMotor
)
from exengine.backends.micromanager import MicroManagerSingleAxisStage as ExEngineMMSingleMotor
from exengine.backends.micromanager import MicroManagerXYStage as ExEngineMMDoubleMotor

class ExEngineSingleMotorModel(MotorModel, ExEngineSingleMotor):
    def __init__(self, name: str, model_info: MotorModelInfo):
        MotorModel.__init__(self, name, model_info)

        # TODO: investigate this initializer
        ExEngineSingleMotor.__init__(self, name, no_executor=False, no_executor_attrs=('_name',))

class ExEngineDoubleMotorModel(MotorModel, ExEngineDoubleMotor):
    def __init__(self, name: str, model_info: MotorModelInfo):
        MotorModel.__init__(self, name, model_info)

        # TODO: investigate this initializer
        ExEngineDoubleMotor.__init__(self, name, no_executor=False, no_executor_attrs=('_name',))

class ExEngineMMSingleMotorModel(MotorModel, ExEngineMMSingleMotor):
    def __init__(self, name: str, model_info: MotorModelInfo):
        MotorModel.__init__(self, name, model_info)
        ExEngineMMSingleMotor.__init__(self, name)

class ExEngineMMDoubleMotorModel(MotorModel, ExEngineMMDoubleMotor):
    def __init__(self, name: str, model_info: MotorModelInfo):
        MotorModel.__init__(self, name, model_info)
        ExEngineMMDoubleMotor.__init__(self, name)

