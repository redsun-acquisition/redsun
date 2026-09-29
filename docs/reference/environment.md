---
icon: lucide/variable
---

# Environment variables

The variables a session sets and reads.
[Services](../explanation/services.md#one-transport-per-session) explains why
a session sets them.

## What a launched service receives

A service a session launches starts with the environment of the session,
and these variables on top of it:

| Variable | Value |
| --- | --- |
| `REDSUN_SERVICE_NAME` | the name the service is declared under |
| `REDSUN_SERVICE_PREFIX` | the `prefix` of the declaration, empty when it has none |
| `PYTHONUTF8` | `1`, so that the service writes UTF-8 |

With the transport `channel-access`:

| Variable | Value |
| --- | --- |
| `EPICS_CA_SERVER_PORT` | a port free on `127.0.0.1` when the service first starts, one for each service |

With the transport `pv-access`:

| Variable | Value |
| --- | --- |
| `EPICS_PVAS_INTF_ADDR_LIST` | `127.0.0.1` |
| `EPICS_PVAS_SERVER_PORT` | `0`, which has the server take a free port |

A service keeps its port while the process of the session runs, through
every restart of the service. A new process of the session chooses another.

A service a session attaches to is started by nobody, and receives nothing.

## What the session changes for itself

A session adds to the address list of its own process, so that its devices
find the services it launched. It keeps what the list already holds, and adds
after it.

| Transport | Variable | Added |
| --- | --- | --- |
| `channel-access` | `EPICS_CA_ADDR_LIST` | `127.0.0.1:<port>`, once for each launched service |
| `pv-access` | `EPICS_PVA_ADDR_LIST` | `127.0.0.1`, once |

A session leaves `EPICS_CA_AUTO_ADDR_LIST` and `EPICS_PVA_AUTO_ADDR_LIST` as
they are. Unless you set them to `NO`, a device also searches the network the
machine is on, and a server there that answers to the same name can be the
one it connects to. Setting them to `NO` does not keep out a server on the
same machine that the address list reaches: under Channel Access, one on the
default port when your own list names `127.0.0.1`; under PVAccess, any server
listening on `127.0.0.1`. A prefix no other server uses is the only way to be
sure.

## What the session reads

| Variable | Read by | Holds |
| --- | --- | --- |
| `QT_API` | `qtpy` | the [Qt binding](../explanation/glossary.md#qt-binding) a Qt session uses, `pyqt6` or `pyside6` |
| `EPICS_CA_ADDR_LIST`, `EPICS_PVA_ADDR_LIST` | the client of the transport | where to look for the services a session attaches to |
