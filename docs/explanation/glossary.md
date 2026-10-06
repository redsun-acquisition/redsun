---
icon: lucide/book-a
---

# Glossary

This glossary explains the terms used across the documentation: those
specific to `redsun`, and those borrowed from the projects it builds on. Each
term is defined once, here, and other pages link to it the first time they
use it.

Acronyms also appear as tooltips across the site: hover a dotted-underlined
word to read it.

### ADR

An ADR (Architecture Decision Record) is a numbered page under
[Decisions](decisions/index.md) that records one
decision and the reasons for it. Once accepted it is never edited; a later ADR
replaces it.

### bluesky

`bluesky` is the library that runs every acquisition in `redsun`. A
[plan](#plan) says what to do; the [`RunEngine`](#runengine) does it and
reports what happened as [documents](#document). Nothing is stored unless
something is listening. See the
[documentation of `bluesky`](https://blueskyproject.io/bluesky/main/index.html).

### Build

A build is what [`Session.build`][redsun.Session.build] does: it reads the
configuration, starts the services, makes every component, connects them and
shows them. It runs as a fixed list of [build steps](#build-step).

### Build step

A build step is one named stage of a [build](#build), such as `services`,
`devices` or `views`. `BUILD_STEPS` lists them in order, so a progress display
knows how many there are.

### Catalog

A catalog is a searchable record of the [runs](#run) a session has done, kept
by a [`tiled`](#tiled) server that the session starts. A session has one when
its `storage` section has a `catalog` key, and a run enters it only when a
component records it there.

### Channel Access

Channel Access is the older of the two network protocols of [EPICS](#epics).
A program uses it to read, set and subscribe to
[process variables](#process-variable).

### Checkpoint

A checkpoint is a point in a [plan](#plan) that the
[`RunEngine`](#runengine) returns to when it resumes after a pause, repeating
what came after it. The term comes from [`bluesky`](#bluesky).

### Component

A component is a [device](#device), a [presenter](#presenter) or a
[view](#view): one of the objects a session makes and owns.

### Configuration

The configuration is the set of settings a session is built from. It comes
from one or more session files or Python dictionaries, applied in order, so
that a later one overrides an earlier one. The keys that say what kind of
session it is must be the same in every source: a disagreement is an error.

### Data key

A data key is the name under which one measured value is recorded in a
[run](#run), such as `camera-sum`. A device chooses the data keys of what it
measures, and often starts them with its own name. The term comes from
[`bluesky`](#bluesky).

### Declaration

A declaration is a line in a session class that says which component to make,
such as `stage: AsDevice[MyStage]`. The attribute name becomes the name of the
component.

### Device

A device is one part of your setup as the session sees it: the values it can
read and set. Devices are written with [`ophyd-async`](#ophyd-async), and
together they model the setup. For now, the preferred way to reach the
hardware is a [service](#service); see [Services](services.md). Devices are
the first [layer](#layer) to be built.

### Device signal

A device signal is one value of a [device](#device) that can be read, set or
both, such as the position of a stage, or an action of the device that can be
triggered. It comes from [`ophyd-async`](#ophyd-async), and is different from
a [signal](#signal) as this glossary defines it.

### Document

A document is a record that the [`RunEngine`](#runengine) emits while a
[plan](#plan) runs: the start of a [run](#run), a description of what is
measured, each measurement, and the stop. The term comes from
[`bluesky`](#bluesky), which explains it on
[its page on documents](https://blueskyproject.io/bluesky/main/documents.html).

### DVP

DVP stands for Device-View-Presenter, the way a `redsun` session is
organised: devices model the setup, presenters hold the behaviour and views
show it. It is Model-View-Presenter with devices in place of the model.

### EPICS

EPICS is a set of tools for controlling instruments over a network. A server
offers values by name, and a program that can reach it reads them and, where
the server allows, sets them. See
[epics-controls.org](https://epics-controls.org/).

### Frontend

A frontend is the part of `redsun` that shows a session on screen, such as the
Qt one. A session file names it by its registered name (`frontend: qt`), and a
package can register its own.

### Hook

A hook is an object you give a session to act at one moment of the
[build](#build), for example to style the application before any window
exists. A hook never changes what the session builds.

### Hook point

A hook point is a named moment at which a [hook](#hook) is called, such as
`configure_application`. Each frontend lists the points it calls, and a
session with no frontend calls none.

### IOC

An IOC (input/output controller) is the server program of [EPICS](#epics). It
offers values as [process variables](#process-variable). Most IOCs read them
from hardware they own; a soft IOC owns none and only holds its values.

### Layer

A layer is one of the three groups a component belongs to: devices, presenters
or views. Layers are built in that order, and a component may only use what
its own layer or an earlier one owns.

### Link

A link is a pair made in [`wire`][redsun.Session.wire]: what sends, then the
[slot](#slot) that receives. What sends is a [signal](#signal) or a
[device signal](#device-signal).

### Manifest

A manifest is the `redsun.yaml` file that a [plugin](#plugin) ships. It lists
the components of the plugin under ids that a session file can name.

### Mocked session

A mocked session is a session whose configuration sets `mock: true`. Its devices
connect to simulated backends that `ophyd-async` provides in place of the
hardware, and the session launches no service, so it runs with no hardware
present.

### ophyd-async

`ophyd-async` is the library devices are written with. It gives a
[device](#device) its [signals](#device-signal) and connects them to the
hardware, directly or through a [service](#service). See the
[documentation of `ophyd-async`](https://blueskyproject.io/ophyd-async/main/index.html).

### Pairing

A pairing is a line of the `pairs` section of a session file, or a
`yield from links_between(a, b)` in `wire`, that connects two
[components](#component) in both directions: each [signal](#signal) of one
reaches each [slot](#slot) of the other that names it. See
[Offer a pairing](../how-to/offer-a-pairing.md).

### Path provider

The path provider is the object that decides where the files of a session go
and what they are called, and creates their folders. Each session has one,
and a device that asks for `path_provider` receives it.

### Placement

A placement is where a view asks to be shown, such as `Dock("left")`. The
frontend decides which placements it can show.

### Plan

A plan is a recipe for an acquisition, written as a Python generator that
yields one instruction at a time. The [`RunEngine`](#runengine) runs it, and a
presenter starts it. The term comes from [`bluesky`](#bluesky), which explains
it on [its page on plans](https://blueskyproject.io/bluesky/main/plans.html).

### Plan widget

A plan widget is the set of controls `redsun` builds for one
[plan](#plan): an input for each parameter, a list of the devices that can
fill a parameter asking for one, and a button to run the plan. A view builds
it from the description of the plan, with `create_plan_widget`.

### Plugin

A plugin is an installed package that offers components to sessions through
its [manifest](#manifest).

### Port

A port is one end of a connection: a [signal](#signal) on the sending side, a
[slot](#slot) on the receiving side. A session file names a port as
`component.port`.

### Prefix

A prefix is the beginning shared by the names of the
[process variables](#process-variable) of one device, such as `CAM:` in
`CAM:Exposure`. The term comes from [EPICS](#epics).

### Presenter

A presenter is the component that holds the behaviour of a session. It talks
to devices and sends signals, but never touches a widget.

### Process variable

A process variable, often written PV, is one named value that an [IOC](#ioc)
offers, such as `CAM:Exposure`, together with its time stamp, its alarm state
and, for a number, its units and limits. A program can read it, set it, or
subscribe to it to be told of every change. The term comes from
[EPICS](#epics).

### Protocol

A protocol is a description of the methods and attributes an object must have.
A component can ask for whatever satisfies a protocol, instead of naming a
class.

### PVAccess

PVAccess is the newer of the two network protocols of [EPICS](#epics). It also
carries structured values, such as an image together with its size.

### Qt binding

A Qt binding is the Python package through which Qt is used: `pyqt6` or
`pyside6`. A session with a window needs one of the two.

### Release

A release is something a [build step](#build-step) registers so that
`shutdown` can undo it later, such as stopping a service. The last release
registered runs first.

### Run

A run is one recording made by a [plan](#plan): everything between a start
[document](#document) and a stop document, under an identifier of its own. A
plan usually makes one run, but may make several or none. The term comes
from [`bluesky`](#bluesky).

### RunEngine

The `RunEngine` is the object of [`bluesky`](#bluesky) that executes a
[plan](#plan). A [presenter](#presenter) creates one and starts plans on it.
`redsun` provides its own,
[`redsun.engine.RunEngine`][redsun.engine.RunEngine].

### Service

A service is a program that owns hardware and offers it to devices under a
[prefix](#prefix). The session starts it, or it already runs elsewhere. A
session stops the services it started when it shuts down.

### Session

A session is one running application: its configuration, its components and
the connections between them. [`Session`][redsun.Session] is the class you
subclass to write one.

### Session file

A session file is a YAML file that holds the
[configuration](#configuration) of a session.

### Setup

Setup is an optional `setup` method that a component defines to receive what
other components own. The session calls it once every component exists.

### Shared value

A shared value is a value that one component makes available to the others,
by marking a method with [`provides`][redsun.provides].

### Signal

A signal is a message that a component sends to every [slot](#slot) connected
to it. Signals are made with `psygnal`; every public one is a [port](#port),
named `sig_snake_case`. A value of a device is a
[device signal](#device-signal), which is a different thing.

### Slot

A slot is a method marked with [`slot`][redsun.slot], which lets other
components connect to it. Its name and arguments are public, since others
rely on them.

### Stack

A stack is a [presenter](#presenter) and a [view](#view) written to work
together: the signals of each match the slots of the other. The session still
builds them as two components and joins them by [wiring](#wiring), so either
can be replaced by one with the same ports. `redsun` ships three: the
positioner (`PositionerPresenter`, `PositionerView`), the light stack
(`LightPresenter`, `LightView`) and the acquisition stack
(`AcquisitionPresenter`, `AcquisitionView`).

### StreamResource

A `StreamResource` is a [document](#document) that names a file or a data
store written by a device or its [service](#service), so that whoever reads
the [run](#run) can find the data. The term comes from
[`bluesky`](#bluesky).

### Strict session

A strict session is a session whose file sets `strict: true`. It stops with an
error if any component fails to build, instead of running without it.

### Structural subtyping

Structural subtyping means deciding whether a class fits by the members it
has, not by what it inherits from. Components never inherit from `redsun` to
be accepted.

### tiled

`tiled` is the server that keeps a [catalog](#catalog). It serves the runs and
their data to a program or a browser over the network. See the
[documentation of `tiled`](https://blueskyproject.io/tiled/).

### Transport

The transport is the network protocol that the services of a session speak:
`channel-access` for [Channel Access](#channel-access), or `pv-access` for
[PVAccess](#pvaccess). The word is the one `fastcs` uses; EPICS clients call
the same choice a provider.

### View

A view is the component that holds the widgets of a session. It shows things
and passes on what the user does, with no behaviour of its own.

### Wiring

Wiring is the choice of which [signal](#signal) reaches which [slot](#slot).
The session decides it, in its `wire` method or in the `wiring` section of its
file; components only declare their [ports](#port).
