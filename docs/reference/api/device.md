# Device

Devices are [ophyd-async](https://bluesky.github.io/ophyd-async/) devices.
Import `Device`, `StandardReadable`, `StandardDetector`, the signal types and
`DeviceMap` from `ophyd_async.core`; see
[Devices](../../explanation/architecture/devices.md).

`redsun.device` adds one protocol on top of that.

::: redsun.device.protocols.HasAsyncShutdown
