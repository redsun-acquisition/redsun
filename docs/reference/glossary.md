---
icon: lucide/book-a
---

# Glossary

The words `redsun` uses, each with one plain definition. Other pages link a
term here the first time they use it, so this is the only place a definition
is written.

Acronyms also appear as tooltips across the site: hover a dotted-underlined
word to read it.

### ADR

Architecture Decision Record. A numbered page under
[Decisions](../explanation/decisions/0001-record-architecture-decisions.md)
that records one decision and the reasons for it. Once accepted it is never
edited; a later ADR replaces it instead.

### Build

What [`Session.build`][redsun.Session.build] does: it reads the configuration,
starts the services, makes every component, connects them, and shows them. It
runs as a fixed list of build steps.

### Build step

One named stage of a build, such as `services`, `devices` or `views`.
`BUILD_STEPS` lists them in order, so a progress display knows how many there
are.

### Catalog

A searchable record of the runs a session has done, kept by a `tiled` server
the session starts. A session has one when its `storage` section has a
`catalog` key.

### Component

A device, presenter or view: one of the objects a session makes and owns.

### Configuration

The settings a session is built from: one or more session files or
mappings, laid on top of each other in order. Later ones win, except for the
keys that say what kind of session it is.

### Declaration

A line in a session class saying which component to make, such as
`stage: AsDevice[MyStage]`. The attribute name is the component's name.

### Device

One part of the setup as the session sees it: the values it can read and
set, written as an `ophyd-async` device. Together the devices model the
setup; the hardware itself is reached through a service. Devices are the
first layer to be built.

### DVP

Device-View-Presenter, the way a `redsun` session is organised: devices talk
to hardware, presenters hold the behaviour, views show it. It is
Model-View-Presenter with devices in place of the model.

### Frontend

The part of `redsun` that shows a session on screen, such as the Qt one. A
session file names it by its registered name (`frontend: qt`), and a package
can register its own.

### Hook

An object you give a session to act at one moment of its build, such as
styling the application before any window exists. A hook never changes what
the session builds.

### Hook point

A named moment at which a hook is called, such as `configure_application`.
Each frontend lists the points it calls; a session with no frontend calls none.

### Layer

One of the three groups a component belongs to: devices, presenters or views.
They are built in that order, and a component may only use what its own layer
or an earlier one owns.

### Manifest

The `redsun.yaml` file a plugin ships, listing its components under ids a
session file can name.

### Path provider

The object that decides where a session's files go and what they are called.
Each session has one, and a device asking for `path_provider` gets it.

### Placement

Where a view asks to be shown, such as `Dock("left")`. The frontend decides
which placements it can show.

### Plan

A `bluesky` recipe for an acquisition, run by the
[`RunEngine`][redsun.engine.RunEngine]. A presenter starts it.

### Plugin

An installed package that offers components to sessions through its manifest.

### Port

One end of a connection: a signal on the sending side, a slot on the
receiving side. A session file names a port as `component.port`.

### Presenter

The component that holds a session's behaviour. It talks to devices and
sends signals, but never touches a widget.

### Protocol

A description of the methods and attributes an object must have. A
component can ask for "whatever satisfies this protocol" instead of naming a
class.

### Release

Something a build step registers so `shutdown` can undo it later, such as
stopping a service. Releases run in the reverse of the order they were
registered.

### Service

A separate process, or a server already running elsewhere, that owns a piece
of hardware and offers it to devices under a prefix. A session starts the
ones it launches and stops them at shutdown.

### Session

One running application: its configuration, its components, and the
connections between them. [`Session`][redsun.Session] is the class you
subclass to write one.

### Session file

A YAML file holding a session's configuration.

### Setup

An optional `setup` method a component defines to receive what other
components own. The session calls it once every component exists.

### Shared value

A value one component makes available to the others, by marking a method with
[`provides`][redsun.provides].

### Signal

A `psygnal` signal a component sends. Every public signal is a port, named
`sig_snake_case`.

### Slot

A method marked with [`slot`][redsun.slot], which lets other components
connect to it. Its name and arguments are public, since others rely on them.

### Strict session

A session whose file sets `strict: true`. It stops with an error if any
component fails to build, instead of running without it.

### Structural subtyping

Deciding whether a class fits by the members it has, not by what it inherits
from. Components never inherit from `redsun` to be accepted.

### Transport

The network protocol a session's services speak: `channel-access` or
`pv-access`.

### View

The component that holds a session's widgets. It shows things and passes on
what the user does, with no behaviour of its own.

### Wiring

Which signal reaches which slot. The session decides it, in its `wire` method
or its file's `wiring` section; components only declare their ports.
