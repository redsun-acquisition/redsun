# Device

The device layer is delegated to
[ophyd-async](https://bluesky.github.io/ophyd-async/): import device
primitives (`Device`, `StandardReadable`, `StandardDetector`, signals,
`DeviceMap`, ...) directly from `ophyd_async.core`. See
[Devices](../../explanation/architecture/devices.md) for guidance.

`redsun.device` hosts only redsun-specific device protocols.

::: redsun.device.protocols.HasAsyncShutdown
