# In-process devices

**In-process** devices provide interaction with the device API in the same process:
  
  - by importing the API as a Python package and use it as a local object: [API via aggregation](#api-via-aggregation);
  - by inheriting from an existing class that encapsulates the commands of your device: [API via inheritance](#api-via-inheritance).

## API via aggregation

"Aggregation" means when an object is constructed inside a class.

In this usage, a standard device is simply a wrapper around the actual device interface you want to control.

The wrapped interface is often referred to as `handler`, although it varies depending on implementation details.
The external application should not interact directly with the `handler` object; instead, the Device wrapping it should take care of calling the appropriate methods of the `handler` to perform the required tasks.

!!! tip
    It is good practice to mark your handler object via a double underscore `__`, i.e. `__handler`, symbolizing that this is a *private* attribute (meaning that only your Device object can use it internally and it is not accessible from the outside). In truth, Python **does not really** enforce private attributes - meaning that there are ways to circumvent the privacy - but it is considered standard practice to annotate them in this manner.

=== "UML"

    ```mermaid
    classDiagram
        class MyDevice {
            -DeviceHandler __handler
            +str name
            +None parent
            configure() None
            read_configuration() dict[str, Reading]
            describe_configuration() dict[str, DataKey]
        }
        class DeviceHandler {
            +int param1
            +float param2
            device_method() void
        }

        MyDevice *-- DeviceHandler
    ```

=== "Python"

    ```python title="my_plugin/device.py"
    from redsun.device import Device
    from device_package import DeviceHandler
    from bluesky.protocols import Reading, Descriptor

    class MyDevice(Device):
        def __init__(self, name: str, /, **kwargs) -> None:
            super().__init__(name, /, **kwargs)

            # unpack the parameters you need
            # to initialize DeviceHandler,
            # or provide them hard-coded
            param1 = kwargs.get("param1", 0)
            param2 = kwargs.get("param2", 0.0)
            self.__handler = DeviceHandler(int_param=param1, float_param=param2, bool_param=True)

        def configure(self) -> None:
            # here goes your implementation;
            self.__handler.configure()

        def read_configuration(self) -> dict[str, Reading]:
            # here goes your implementation;
            return self.__handler.read_configuration()

        def describe_configuration(self) -> dict[str, Descriptor]:
            # here goes your implementation;
            return self.__handler.describe_configuration()
    ```

Furthermore, a single Device can encapsulate multiple handlers, each of them with different functionalities. Keep in mind that it is your responsability (as developer) to associate the execution of Bluesky messages with the appropriate device handler.

```python title="my_plugin/device.py"

# a dummy representation of a plugin package that encapsulates
# a Device wrapping controls for a camera and a motor
from redsun.device import Device
from device_package import CameraHandler, MotorHandler

class MyDevice(Device):
    def __init__(self, name: str, /, **kwargs) -> None:
        super().__init__(name, **kwargs)

        self.__motor_handler = MotorHandler(**kwargs.get("motor_parameters", {}))
        self.__camera_handler = CameraHandler(**kwargs.get("camera_parameters", {}))

```

## API via inheritance

Using aggregation to control your device interface may be impractical if `DeviceHandler` already leverages a lot of internal code. Inheriting your Device from a pre-existing class gives the benefit of reusing it without having to rewrite any of the internals.

=== "UML"

    ```mermaid
    classDiagram
        class MyDevice {
            +str name
            +None parent
            configure() None
            read_configuration() dict[str, Reading]
            describe_configuration() dict[str, DataKey]
        }
        class DeviceHandler {
            device_method() void
        }

        MyDevice <|-- DeviceHandler
    ```

=== "Python"

    ```python title="my_plugin/device.py"
    from redsun.device import Device
    from device_package import DeviceHandler
    from bluesky.protocols import Reading, Descriptor

    class MyDevice(Device, DeviceHandler):
        def __init__(self, name: str, /, **kwargs) -> None:
            super().__init__(name, **kwargs)

        def configure(self) -> None:
            # here goes your implementation;
            super().configure()

        def read_configuration(self) -> dict[str, Reading]:
            # get the current configuration values
            config = super().get_settings_values()

            # whatever output is returned, it must
            # be converted to a dictionary of readings

            return super().describe_configuration()

        def describe_configuration(self) -> dict[str, Descriptor]:
            # first get whatever description your device provides
            config = super().get_settings_description()

            # whatever output is returned, it must
            # be converted to be a dictionary of descriptors
            reading = convert_to_reading(config) # your implementation

            return reading
    ```

Just like in the aggregated API, your device can also inherit from multiple classes. Again, it is your responsibility (as developer) to ensure that the appropriate Bluesky protocols are invoked on the correct device.

```python title="my_plugin/device.py"

# a dummy representation of a plugin package that encapsulates
# a Device wrapping controls for a camera and a motor
from redsun.device import Device
from device_package import CameraHandler, MotorHandler

class MyDevice(Device, CameraHandler, MotorHandler):
    def __init__(self, name: str, **kwargs) -> None:
        super().__init__(name, **kwargs)
```

## Key differences

Although they may initially look similar, there are key differences and advantages in each approach.

Aggregation is useful...
- ... when you want to have a more fine-grained control over your device;
- ... when your device interface doesn't have an actual class encapsulating methods and parameters but instead uses a different programming paradigm;
- ... when you don't want to expose certain behaviors of your device to the end-user (a.k.a. inhibiting the possibility to call public methods);
- ... when your device interface is built using another language (C++, Rust, ...) and you want to keep a minimal level of abstraction between the device and the handler;
- ... when your handler actually controls the interaction with multiple devices topology and you want to expose only a sub-set of those functionalities.

An example candidate for aggregation is the [`pymmcore-plus`] package, which wraps the controls of multiple Micro-Manager devices behind the [`CMMCorePlus`] interface and provides additional functionalities (such as the [`MDAEngine`]).

Inheritance is useful...
- ... when your device has a lot of code and you want to quickly wrap it to be Bluesky-compatible;
- ... when it provides extra functionalities that allow to work with remote devices by default;
- ... when it is already a Bluesky-compatible device and you just want to make it as a plugin for Redsun.

Example candidates for inheritance are the [`microscope`] and [`openwfs`] packages, as they provide pre-configured interfaces that can be extended with additional Bluesky methods.

[`pymmcore-plus`]: https://pymmcore-plus.github.io/pymmcore-plus/
[`cmmcoreplus`]: https://pymmcore-plus.github.io/pymmcore-plus/api/cmmcoreplus/
[`mdaengine`]: https://pymmcore-plus.github.io/pymmcore-plus/guides/mda_engine/
[`microscope`]: https://python-microscope.org/
[`openwfs`]: https://github.com/IvoVellekoop/openwfs
