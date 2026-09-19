# Glossary

Terms as `redsun` uses them, including ones that look like ordinary English.

Acronyms and rarer terms also appear as tooltips across the site: hover a
dotted-underlined word to read its definition.

### Application container

The object a session is. It declares the components, builds them in order,
registers their providers, wires them together and injects their dependencies.
[`AppContainer`][redsun.containers.container.AppContainer] is the base;
[`QtAppContainer`][redsun.qt.QtAppContainer] is the Qt one.

### ADR

Architecture Decision Record. A numbered document under
`docs/explanation/decisions` recording one decision and its reasons. An
accepted ADR is never edited; a later one supersedes it.

### Build step

One stage of `AppContainer.build`, announced by name as it starts.
`AppContainer.BUILD_STEPS` lists them in order, so a progress display can size
itself from it.

### Component

A device, presenter or view: the three kinds of object a container declares,
builds and owns.

### DVP

Device-View-Presenter, the architecture of a `redsun` session.
Model-View-Presenter with a Device layer in place of the Model, and with
presenters and views talking through the virtual container instead of holding
references to each other.

### Device

Hardware, or a stand-in for it, as an `ophyd-async` device. Hardware access is
asynchronous. A device that fails to build is logged and skipped like any
component, so a missing instrument does not abort the session.

### Frontend

The toolkit a session's views use, named in the configuration as `pyqt` or
`pyside`. It picks the container class `AppContainer.from_config` builds on.

### Hook

An object a session installs on its container to act at one point of the
build. A hook never changes what the container builds or in which order.

### Hook point

A named moment of the build at which a hook is called, named after the method
it calls: `create_application`, `configure_application`, `during_build`,
`configure_main_view`. Each point belongs to a toolkit, whose container
declares it.

### Plan

A `bluesky` generator describing an acquisition, run by the
[`RunEngine`][redsun.engine.RunEngine]. A presenter launches it; the engine
runs it and emits its documents.

### Port

One end of a connection: a signal on the sending side, a slot on the receiving
side. A configuration file addresses a port as `component.port`.

### Presenter

The component holding a session's behaviour. It owns devices, exposes signals
and slots, and never touches a widget. Its constructor starts with
`(name, devices)`.

### Provider key

A typed key under which a component puts a value in the virtual container, so
another component can resolve it without knowing who produced it.

### Session

One running application: its configuration, components and the connections
between them.

### Signal

A `psygnal` signal a component emits. Every public signal attribute is a port,
named `sig_snake_case`.

### Slot

A method marked with [`slot`][redsun.virtual.slot], which makes it
connectable. Its name and signature become public API, since other components
connect to them.

### Path provider

The object giving a session's files their directory and name,
[`SessionPathProvider`][redsun.path_provider.SessionPathProvider]. One per
session, built by the container and passed to every device taking a
`path_provider` keyword.

### Structural subtyping

A class conforms by the members it has, not by what it inherits. Presenters and
views are checked against `@runtime_checkable` protocols on the built instance,
so a component never inherits from `redsun` to satisfy one.

### View

The component holding a session's widgets. It declares signals and slots and
no behaviour of its own. Its constructor takes `(name)` alone.

### Virtual container

The session-wide signal bus, provider registry and document-callback registry
in one object. Components reach each other through it instead of holding
references.

### Wiring

Which signal reaches which slot. The application declares it, not the
components: a component declares its ports and the session connects them.
