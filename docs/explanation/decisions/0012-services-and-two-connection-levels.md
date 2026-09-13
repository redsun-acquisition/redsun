# 12. Services and two connection levels

Date: 2026-09-13

## Status

Accepted.

## Context

A session's devices increasingly talk to hardware through a server rather than
a driver in the session process: an EPICS IOC, written with caproto or taken
from an existing facility, running as a process the session starts or as a
container beside it. ophyd-async already speaks to such servers; what a session
lacked was any notion of the server itself. Each application started its IOCs
from test code or by hand, stopped them with `Popen.terminate()`, and had no
way to hand a device the prefix of the server it should use.

Several questions had to be answered before anything could be built:

- **Constructing an EPICS device.** The container built a device as
  `cls(name, **kwargs)`, and an `EpicsDevice` takes `prefix` first, so declaring
  one raised `got multiple values for argument 'prefix'`. One answer was an
  `EpicsServiceDevice` base class carrying the service; another was building
  every device by keyword.
- **Stopping a process.** Measured on Windows and Linux, against a stand-in
  service and a caproto IOC with a shutdown hook: `terminate()` and `kill()`
  skip cleanup on both; `SIGINT` runs it on Linux only; a console control
  event runs it on Windows only in a process with a console, and a process
  started without a console window, as a Qt application must start them, never
  receives one. A service that watches its standard input and ends when it
  closes cleaned up on both, including when the parent process died.
- **Several services on one host.** Two caproto IOCs on the default port both
  answered on Linux; on Windows the second was never found. Giving each its own
  `EPICS_CA_SERVER_PORT` and listing `127.0.0.1:<port>` in the client's
  `EPICS_CA_ADDR_LIST` made both answer on both.
- **What belongs in the framework.** An earlier plan also put an identity
  check, a heartbeat watch, a standby command and live-view resolution into
  the container. Each was built and then taken out: the identity check and the
  heartbeat depend entirely on what an IOC publishes and can be written in a
  presenter; standby, for now, only triggers commands a presenter can trigger
  itself; nothing in redsun shows a live view.

## Decision

- **A service is data, not a class.** It is declared with a module to run and
  the line it prints once ready, or with neither for a service that is already
  running. `redsun.services.Service` is the handle a container makes from that
  declaration; nobody subclasses it.
- **Two connection levels, kept apart.** The session connects to a service with
  ophyd-async's `connect()`. The service connects to its hardware, driven over
  process variables. Nothing in the framework opens or chooses hardware.
- **Devices are built by keyword**, as `cls(name=<name>, **kwargs)`, and a
  device naming a service receives its prefix as `prefix`. There is no
  `EpicsServiceDevice`: a stock ophyd-async device takes part unchanged.
- **Services live outside the build.** Starting them is the first build step,
  connecting devices the step after building them. Stopping them runs on every
  shutdown, built or not, and before the session's log file closes, and a build
  that raises stops them before it propagates.
- **Stopping is closing standard input, then `SIGINT` on POSIX, then killing**,
  each step waiting a per-service timeout. A service written for redsun watches
  its standard input.
- **Each launched service gets a Channel Access port of its own** for the life
  of the session process, and the container closes the process's Channel
  Access channels once it has stopped the services it launched.
- **Identity checks, heartbeats, standby and live-view resolution stay out**
  until the container has a part in them that an application cannot play. For
  standby that part is dropping connections and stopping services, which waits
  for ophyd-async to disconnect a device.

## Consequences

- Declaring a device whose constructor takes `name` positional-only no longer
  works; the constructor has to accept it by keyword, as ophyd-async's base
  classes do.
- A service that ignores its standard input is stopped by `SIGINT` on POSIX but
  killed on Windows, without cleanup. Service authors are told to watch
  standard input and to clean up before writing to standard output, which is
  closed once the session is gone.
- libca reads `EPICS_CA_ADDR_LIST` once per process. A container built again
  reaches its services, which keep their ports; a second container launching
  services under other names in the same process cannot reach them on Windows.
- Closing Channel Access channels after stopping services closes every channel
  in the process, not only those of the stopped services: libca offers nothing
  narrower.
- An application wanting to know that its service is the intended one, or
  still alive while its process runs, reads or subscribes to the service's
  signals itself.
