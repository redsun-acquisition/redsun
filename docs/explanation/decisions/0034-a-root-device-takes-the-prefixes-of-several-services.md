# 34. A root device takes the prefixes of several services

Date: 2026-10-25

## Status

Accepted

## Context

[ADR 33](0033-device-trees-one-index-of-every-device.md) lets a session
declare a whole setup as one root device, but the root could reach only one
[service](../glossary.md#service). A device declared with `service="x"` gets
that service's [prefix](../glossary.md#prefix) as its `prefix` argument, and
nothing else. So a microscope whose stage and camera sit behind two services
could not be one device, and the session had to declare each piece, each
child device such as the stage or the camera, on its own.

The declaration had to say which prefix goes where, and the build had to
decide what to do when one of the services does not start. A whole root
dropped because its camera's service crashed hides a stage that works. A
root built without its camera, with nobody told, hides the crash.

## Decision

- **A declaration maps each constructor keyword to a service.** `services`
  takes the keyword as its key and the service's name as its value, in
  `Declare` and in the session file alike. `service="x"` stays, and means
  `services={"prefix": "x"}`. Two keywords may name one service. The device
  class names its prefixes, never the services behind them, so the session
  file still decides how the setup is reached.
- **The constructor says which pieces are optional.** A keyword whose
  default is `None` is optional. When its service does not start, the session
  leaves the keyword out and the device builds without that piece. A keyword
  with any other default, or none, is required, and the device is skipped as
  before. A default such as `"CAM:"` counts as required, because building the
  camera on a made-up prefix would hide the failure.
- **The build summary names what is missing.** A device built without a piece
  gets a `Built without` line, and every service that did not start gets a
  `Services not started` line.
- **A strict session stops on a service that did not start**, whether or not
  a device names it. Until now a strict session stopped only on a component
  it could not build. A microscope built without its camera counts as built,
  so that rule alone lets the session run without the camera. The camera is
  left out only because its service did not start, so a session that stops
  on that service never runs without the camera.
- **A declaration the session cannot read raises `TypeError`**, as `service`
  together with `prefix` already did: `service` together with `services`, a
  keyword both mapped and given, and a keyword the constructor does not take.

### Before

Each piece is a device of its own, on its own service:

```python
class MyApp(QtSession):
    stage: Annotated[AsDevice[MyStage], Declare(service="stage_ioc")]
    camera: Annotated[AsDevice[MyCamera], Declare(service="camera_ioc")]
```

### After

One root holds both pieces, and its camera is optional:

```python
class MyMicroscope(StandardReadable):
    def __init__(
        self,
        stage_prefix: str,
        camera_prefix: str | None = None,
        name: str = "",
    ) -> None:
        self.xy = MyStage(stage_prefix)
        if camera_prefix is not None:
            self.camera = MyCamera(camera_prefix)
        super().__init__(name=name)


class MyApp(QtSession):
    microscope: Annotated[
        AsDevice[MyMicroscope],
        Declare(
            services={"stage_prefix": "stage_ioc", "camera_prefix": "camera_ioc"}
        ),
    ]
```

When `camera_ioc` does not start, the session still has the microscope and
its stage, and the summary says what it left out:

```text
Session built: 1/1 devices, 0/0 presenters, 0/0 views
Built without: microscope (camera_prefix: camera_ioc not started)
Services not started: camera_ioc (exited with code 3 before it was ready)
```

Other options were rejected:

- Letting the session build each piece from its own declaration and pass the
  built devices into the root. Each piece would be declared twice, once on
  its own and once as a child, and the session would have to order the
  devices it builds.
- A constructor argument mapping service names to prefixes. The device class
  would then name the services, which belong to the session file.
- Keeping a root whose piece started but does not answer when it connects.
  `ophyd-async` connects a root and its children as one unit, so a camera that
  does not answer fails the whole microscope, and the session drops it as it
  drops any device that does not connect.

## Consequences

- A setup whose pieces sit behind several services can be one root device,
  and its stage keeps working when the camera's service does not start.
- A strict session that declares a service nobody uses now stops when that
  service does not start, where it used to run on. The
  [migration page](../../how-to/migrate-from-0.15.md) says what to change.
- A device declared with `service=` whose `prefix` defaults to `None` now
  builds without a prefix when its service does not start, where it was
  skipped before.
- `services` is a reserved keyword, like `service`, so a device class can't
  take one of its own.
