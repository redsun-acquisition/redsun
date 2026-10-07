---
icon: lucide/book-a
---

# Glossary

This glossary explains the words used across the documentation, both the ones
specific to `redsun` and the ones borrowed from the projects it builds on.
Each term is defined once, here, and other pages link to it the first time
they use it.

Acronyms also show up as tooltips across the site: hover over a word with a
dotted underline to read what it stands for.

### ADR

An ADR (Architecture Decision Record) is a numbered page under
[Decisions](decisions/index.md) that records one
decision and the reasons for it. Once accepted, it's never edited; a later ADR
replaces it instead.

### Attached service

An attached service is a [service](#service) that already runs, in a
container or on another host, and that you declare with `Attach`. The session
neither starts nor stops it, and only passes its [prefix](#prefix) on to the
devices that name it.

### Autoconnect

`autoconnect` is the keyword of a device [declaration](#declaration) that
says whether the [build](#build) connects the device, and it is `true` unless
you set it. A device declared with `autoconnect=False` stays unconnected until
your session's code connects it.

### bluesky

`bluesky` is the library that runs every acquisition in `redsun`. A
[plan](#plan) says what to do, and the [`RunEngine`](#runengine) does it and
reports what happened as [documents](#document). Nothing is stored unless
something is listening for those documents. See the
[documentation of `bluesky`](https://blueskyproject.io/bluesky/main/index.html).

### Build

A build is what [`Session.build`][redsun.Session.build] does. It reads the
configuration and starts the toolkit the session runs on, such as Qt, then
runs a fixed list of [build steps](#build-step) that start the services, make
every component, connect them and show them.

### Build step

A build step is one named stage of a [build](#build), such as `services`,
`devices` or `views`. `BUILD_STEPS` lists them in order, so a progress display
knows how many there are.

### Callback

A callback, or document callback, is an object that receives the
[documents](#document) of a [run](#run): a `DocumentRouter`, or anything you
can call as `(name, doc)`. A plan can require callbacks of its own, and the
[plan widget](#plan-widget) lets the user attach more.

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
that a later one overrides an earlier one. Three keys say what kind of
session it is, `schema_version`, `frontend` and `services.transport`, so every
source that gives one of them must give the same value, or the session stops
with an error.

### Data key

A data key is the name under which one measured value is recorded in a
[run](#run), such as `camera-sum`. A device chooses the data keys of what it
measures, and often starts them with its own name. The term comes from
[`bluesky`](#bluesky).

### Declaration

A declaration says which [component](#component) a session makes. It is a
line in the session class, such as `stage: AsDevice[MyStage]`, or an entry in
the `devices`, `presenters` or `views` section of a
[session file](#session-file), which declares a component even when the class
doesn't. The attribute name, or the key of the entry, becomes the name of the
component.

### Derived product

A derived product is an array that a component computes from a [run](#run)
and keeps next to the data it came from, such as a median over a scan. A
[writer](#writer) stores it; see
[How derived products are stored](derived-products.md).

### Device

A device is one part of your setup as the session sees it: the values it can
read and set. You write devices with [`ophyd-async`](#ophyd-async), and
together they model the setup. For now, the preferred way to reach the
hardware is a [service](#service); see [Services](services.md). Devices are
the first [layer](#layer) to be built.

### Device signal

A device signal is one value of a [device](#device) that can be read, set or
both, such as the position of a stage, or an action of the device that you
can trigger. It comes from [`ophyd-async`](#ophyd-async), and is different from
a [signal](#signal) as this glossary defines it.

### Document

A document is a record that the [`RunEngine`](#runengine) emits while a
[plan](#plan) runs: the start of a [run](#run), a description of what is
measured, each measurement, and the stop. The term comes from
[`bluesky`](#bluesky), which explains it on
[its page on documents](https://blueskyproject.io/bluesky/main/documents.html).

### DVP

DVP stands for Device-View-Presenter, the way a `redsun` session is
organised: [devices](#device) model the setup, [presenters](#presenter) hold
the application logic, and [views](#view) show the state of the session and
pass on the user's input. It follows Model-View-Presenter, a pattern that
keeps what the user sees apart from the logic behind it, with devices in place
of the model. Devices reach the hardware directly or, preferably, through
[services](#service).

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

A hook is an object you give a session so you can act at a given point of its
life, for example to style the application before any window exists, or to
ask the user before the window closes. A hook never changes what the session
builds.

### Hook point

A hook point is a named point at which a [hook](#hook) is called, such as
`configure_application` before any view is made, or `confirm_close` when the
window is about to close; `during_build` lasts the whole [build](#build).
Each [frontend](#frontend) lists the points it calls, and a session with no
frontend calls none.

### IOC

An IOC (input/output controller) is the server program of [EPICS](#epics). It
offers values as [process variables](#process-variable). Most IOCs read them
from hardware they own; a soft IOC owns none and only holds its values.

### Launched service

A launched service is a [service](#service) that you declare with `Launch`,
so the session runs it as `python -m <module>` while it builds and stops it
when it shuts down.

### Layer

A layer is one of the three groups a component belongs to: devices, presenters
or views. Layers are built in that order, so a component's
[`setup`](#setup) can only ask for what its own layer or an earlier one owns,
and its constructor for no other component at all. [Signals](#signal) and
[slots](#slot) connect across layers in either direction.

### Link

A link is a pair made in [`wire`][redsun.Session.wire]: what sends, then the
[slot](#slot) that receives. What sends is a [signal](#signal) or a
[device signal](#device-signal).

### Manifest

A manifest is a YAML file, of any name, that a [plugin](#plugin) ships and
registers under the `redsun.plugins` entry point of its package; `redsun`
registers its own as `plugins.yaml`. It lists the devices, presenters, views
and services of the plugin, and its [providers](#provider), under ids that a
session file can name.

### Mocked session

A mocked session is a session whose configuration sets `mock: true`. Its devices
connect to simulated backends that `ophyd-async` provides in place of the
hardware, and the session launches no service, so it runs with no hardware
present.

### ophyd-async

`ophyd-async` is the library devices are written with. It gives a
[device](#device) its [device signals](#device-signal) and connects them to the
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

A placement is where a [view](#view) asks to be shown, such as
`Dock("left")`. The [frontend](#frontend) decides which placements it can
show.

### Plan

A plan is a recipe for an acquisition, written as a Python generator that
yields one instruction at a time. The [`RunEngine`](#runengine) runs it, and a
presenter starts it. The term comes from [`bluesky`](#bluesky), which explains
it on [its page on plans](https://blueskyproject.io/bluesky/main/plans.html).

### Plan widget

A plan widget is the set of controls `redsun` builds for one
[plan](#plan): an input for each parameter, a list of the devices that can
fill a parameter asking for one, and a button to run the plan. A view builds
it with `create_plan_widget` from the
[`PlanSpec`][redsun.presenter.plan_spec.PlanSpec] of the plan, a description
read from the plan's signature.

### Plugin

A plugin is an installed package that offers components, services and
[providers](#provider) to sessions through its [manifest](#manifest).

### Port

A port is one end of a connection: a [signal](#signal) on the sending side, a
[slot](#slot) on the receiving side. A session file names a port as
`component.port`.

### Prefix

A prefix is the beginning shared by the names of a group of
[process variables](#process-variable), such as `CAM:` in `CAM:Exposure`. A
[service](#service) has one and gives it to every device that names the
service. The term comes from [EPICS](#epics).

### Presenter

A presenter is a [component](#component) with no [placement](#placement),
which holds the application logic. It runs [plans](#plan), reacts to
[documents](#document), moves devices and sends signals, but never touches a
widget.

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

### Provider

A provider is a class the session makes before any component, only to share
values: each method it marks with [`provides`][redsun.provides] gives a
[shared value](#shared-value). You list providers in the `providers`
attribute of the session class, or in the `providers` section of a session
file, which names them by their id in a plugin's [manifest](#manifest).

### psygnal

`psygnal` is the library that `redsun` makes [signals](#signal) with. It
doesn't need Qt, so components can send signals in a session with no window.
See the [documentation of `psygnal`](https://psygnal.readthedocs.io/).

### PVAccess

PVAccess is the newer of the two network protocols of [EPICS](#epics). It also
carries structured values, such as an image together with its size.

### Qt binding

A Qt binding is the Python package through which Qt is used: `pyqt6` or
`pyside6`. A session with a window needs one of the two.

### Readback

The readback is the [device signal](#device-signal) that says where a movable
device is, such as the position a stage reports. `ophyd-async` names it,
together with the [setpoint](#setpoint), in the `movable_logic` of a
`StandardMovable`.

### Release

A release is something a [build step](#build-step) registers so that
`shutdown` can undo it later, such as stopping a service. Releases run in
reverse order, so the last one registered runs first.

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

A service is a server that devices talk to, such as an [IOC](#ioc), and it
gives its [prefix](#prefix) to each device that names it. The session launches
it as a process of its own, or attaches to one already running elsewhere, and
stops the services it launched when it shuts down.

### Session

A session is one running application: its configuration, its components and
the connections between them. [`Session`][redsun.Session] is the class you
subclass to write one.

### Session file

A session file is a YAML file that holds all or part of the
[configuration](#configuration) of a session. Its `services`, `devices`,
`presenters` and `views` sections declare the components, `wiring` and
`pairs` connect them, and keys such as `frontend`, `strict` and `storage` set
up the session as a whole.

### Setpoint

The setpoint is the [device signal](#device-signal) you write to move a
movable device, such as the position a stage is sent to. `ophyd-async` names
it, together with the [readback](#readback), in the `movable_logic` of a
`StandardMovable`, and one signal can be both.

### Setup

Setup is an optional `setup` method that a [component](#component) defines to
receive what other components own. The session calls it once every component
exists.

### Shared value

A shared value is a value that a component, or a [provider](#provider), makes
available to the others by marking a method with
[`provides`][redsun.provides]. A component asks for a shared value by its type
in `setup`, or in its constructor when a provider shares it.

### Signal

A signal is a message that a component sends, through
[`psygnal`](#psygnal), to every [slot](#slot) connected to it, and by
convention its name starts with `sig_`.
Each public signal is a [port](#port), as is each member of a `SignalGroup`
the component holds. A value of a device is a
[device signal](#device-signal), which is a different thing.

### Slot

A slot is a method marked with [`slot`][redsun.slot], which lets other
components connect to it. Its name and arguments are public, because other
components rely on them.

### Stack

A stack is a [presenter](#presenter) and a [view](#view) written to work
together: each slot of one names, with `slot(signal=...)`, the signal of the
other that reaches it. The session still builds them as two components, and a
[pairing](#pairing) joins them, so either can be replaced by one with the
same ports. `redsun` ships three: the
positioner (`PositionerPresenter`, `PositionerView`), the light stack
(`LightPresenter`, `LightView`) and the acquisition stack
(`AcquisitionPresenter`, `AcquisitionView`).

### StreamDatum

A `StreamDatum` is a [document](#document) that follows a
[`StreamResource`](#streamresource) and says which part of the data it names
belongs to which measurements of the [run](#run). The term comes from
[`bluesky`](#bluesky).

### StreamResource

A `StreamResource` is a [document](#document) that names a file or a data
store written by a device or its [service](#service), so that whoever reads
the [run](#run) can find the data. The term comes from
[`bluesky`](#bluesky).

### Strict session

A strict session is a session whose configuration sets `strict: true`. If any
component fails to build, or its `setup` fails, the session stops with an
error instead of running without the component.

### Structural subtyping

Structural subtyping means deciding whether a class fits by the members it
has, not by what it inherits from. A component never has to inherit from a
`redsun` class to be accepted.

### tiled

`tiled` is the server that keeps a [catalog](#catalog). It serves the runs and
their data to a program or a browser over the network. See the
[documentation of `tiled`](https://blueskyproject.io/tiled/).

### Toolkit

A toolkit is the GUI library a [frontend](#frontend) shows views with, such
as Qt. Only the frontend's own package imports it, so a session without a
window doesn't need it installed.

### Transport

The transport is the network protocol that every service of a session speaks,
set by the `services.transport` key: `channel-access` for
[Channel Access](#channel-access), the default, or `pv-access` for
[PVAccess](#pvaccess). The word comes from `fastcs`, a library for writing
services, which [How to write a service](../how-to/write-a-service.md) uses.

### View

A view is a [component](#component) with a [placement](#placement), which
says where it is shown. It holds widgets, shows the state of the session and
passes on what the user does, with no application logic of its own.

### Wiring

Wiring is the choice of which [signal](#signal) reaches which [slot](#slot).
The session decides it, in its `wire` method or in the `wiring` and `pairs`
sections of its file, where each line of `pairs` is a [pairing](#pairing);
components only declare their [ports](#port).

### Writer

[`Writer`][redsun.writers.Writer] is the class that writes the
[derived products](#derived-product) of a component into the stores a run
names. The component forwards it the documents of the run, which give the
layout and store of each product, and hands it the data with `append` or
`write`.
