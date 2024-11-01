import importlib
import inspect
import os
import weakref
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from typing import Optional, Union

	from redsun.toolkit.config import ControllerInfo, RedSunInstanceInfo
	from redsun.toolkit.controller import ComputationalController, DeviceController
	from redsun.toolkit.engine import EngineHandler
	from redsun.toolkit.virtualbus import VirtualBus

# Initialize an empty dictionary for the handlers
HANDLERS = {}

# Define the base path for the engine directory
ENGINE_PATH = os.path.join(os.path.dirname(__file__), "engine")

# Dynamically load all engine handlers
for filename in os.listdir(ENGINE_PATH):
	# Only consider Python files (ignoring __init__.py or any non-handler files)
	if filename.endswith(".py") and filename not in ["__init__.py"]:
		module_name = (
			f"redsun.controller.engine.{filename[:-3]}"  # Module name without ".py"
		)
		module = importlib.import_module(module_name)  # Import the module

		# Iterate through all classes in the module
		for name, obj in inspect.getmembers(module, inspect.isclass):
			# Check if the class is a subclass of EngineHandler (to ensure it's a valid handler)
			if "EngineHandler" in [base.__name__ for base in obj.__bases__]:
				# Add the class to the handlers dictionary
				HANDLERS[filename[:-3].lower()] = obj


def create_engine(
	info: "RedSunInstanceInfo", virtual_bus: "VirtualBus", module_bus: "VirtualBus"
) -> "EngineHandler":
	"""Creates the proper engine handler based on the instance configuration.

	Parameters
	----------
	info : RedSunInstanceInfo
	    RedSun instance configuration dataclass.
	virtual_bus : VirtualBus
	    Intra-module virtual bus.
	module_bus : VirtualBus
	    Inter-module virtual bus.

	Returns
	-------
	EngineHandler
	    Engine handler instance. The `EngineHandler` abstract class provides the API interface for all engine handlers.

	Raises
	------
	ValueError
	    If the engine type is not recognized.
	"""
	try:
		handler = HANDLERS[info.engine]
	except KeyError:
		raise ValueError(f"Unknown engine: {info.engine}")
	return handler(info, virtual_bus, module_bus)  # type: ignore[no-any-return]


# TODO: this factory should construct the controllers
# based on the plugin information; hence it requires a dynamic
# loading mechanism for the controllers
class ControllerFactory:
	"""Controller factory class.

	Parameters
	----------
	virtual_bus : VirtualBus
	    Intra-module virtual bus.
	module_bus : VirtualBus
	    Inter-module virtual bus.
	"""

	__controllers: weakref.WeakValueDictionary[
		str, "Union[DeviceController, ComputationalController]"
	] = weakref.WeakValueDictionary()

	def __init__(self, virtual_bus: "VirtualBus", module_bus: "VirtualBus") -> None:
		self.__virtual_bus = virtual_bus
		self.__module_bus = module_bus

	def build(
		self, info: "ControllerInfo"
	) -> "Optional[Union[DeviceController, ComputationalController]]":
		"""Build a controller based on the provided information. The created controller is stored
		in the factory class with a weak reference for future access during application shutdown.

		Parameters
		----------
		info : ControllerInfo
		    Controller information dataclass.

		Returns
		-------
		Union[DeviceController, ComputationalController]
		    Controller instance.
		"""
		return None
