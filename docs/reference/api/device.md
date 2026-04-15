# Device

The `redsun.device` module re-exports the ophyd-async device primitives.
Import from here rather than directly from `ophyd_async` in application code.

## Base classes

::: redsun.device.Device

::: redsun.device.StandardReadable

::: redsun.device.StandardDetector

::: redsun.device.StandardFlyer

## Acquisition protocols

::: redsun.device.DetectorController

::: redsun.device.DetectorWriter

::: redsun.device.FlyerController

## Trigger configuration

::: redsun.device.TriggerInfo

::: redsun.device.DetectorTrigger

## Signals

::: redsun.device.SignalR

::: redsun.device.SignalRW

::: redsun.device.SignalW

::: redsun.device.SignalX

## Soft signals

::: redsun.device.soft_signal_rw

::: redsun.device.soft_signal_r_and_setter

## Status

::: redsun.device.AsyncStatus

::: redsun.device.WatchableAsyncStatus

## Protocols

::: redsun.device.protocols
    options:
      members:
        - HasCache
