# Glossary

The vocabulary these pages are written in. Terms that read as ordinary English
elsewhere are defined here in the sense redsun uses them.

Acronyms and the less common terms below also appear as tooltips throughout the
documentation: hover a dotted-underlined word to read its definition without
leaving the page.

### Application container

The object a session is: it declares the components, builds them in order,
registers their providers, wires them together and injects their dependencies.
[`AppContainer`][redsun.containers.container.AppContainer] is the base;
[`QtAppContainer`][redsun.qt.QtAppContainer] is the one a Qt session uses.

### ADR

Architecture Decision Record. A numbered document under
`docs/explanation/decisions` recording one decision and the reasoning behind
it. An ADR is never edited once accepted; a later one supersedes it.

### Build step

One stage of `AppContainer.build`, announced by name as it starts.
`AppContainer.BUILD_STEPS` names them in order, so a progress display sizes
itself from the framework rather than from a count of its own.

### Component

A device, a presenter or a view: the three kinds of object a container
declares, builds and owns.

### DVP

Device-View-Presenter, the architecture a redsun session is built on. It is
Model-View-Presenter with the Model layer replaced by a Device layer, and with
the presenters and views decoupled from each other through the virtual
container rather than holding references to one another.

### Device

A piece of hardware, or a stand-in for one, as an `ophyd-async` device.
Hardware access is asynchronous throughout. A device that fails to build is
logged and skipped, so a missing instrument does not abort the session.

### Frontend

The toolkit a session's views are written against, named in the configuration
as `pyqt` or `pyside`. It selects the container class a
`AppContainer.from_config` session is built on.

### Hook

An object a session installs on its container to act at one point in the
build. A hook never changes what the container builds or the order it builds
it in; it acts at a moment the container reaches anyway.

### Hook point

A named moment in the build at which a hook is called, named after the method
it calls: `create_application`, `configure_application`, `during_build`,
`configure_main_view`. Every point belongs to a toolkit, so a toolkit
container declares them.

### Plan

A bluesky generator describing an acquisition, run by the
[`RunEngine`][redsun.engine.RunEngine]. A presenter launches one; the engine
executes it and emits the documents it produces.

### Port

One end of a connection: a signal on the publishing side, a slot on the
consuming side. A port is addressed as `component.port` in a configuration
file.

### Presenter

The component holding a session's behaviour. It owns devices, exposes signals
and slots, and never touches a widget. Its constructor leads with
`(name, devices)`.

### Provider key

A typed key a component binds a value to in the virtual container, so another
component can resolve it without knowing who produced it.

### Session

One running application: its configuration, its components, and the
connections between them.

### Signal

A psygnal signal a component emits. Every public signal attribute is a port,
named `sig_snake_case`.

### Sink

The producer's face of a storage queue. A device holding a
[`FrameSink`][redsun.storage.FrameSink] can put frames and close it, and
nothing else.

### Slot

A method marked with [`slot`][redsun.virtual.slot], making it connectable.
Marking a method makes its name and signature public API, since that is what
other components are connected against.

### Storage backend

The mechanics of writing to one storage format, split in two:
[`StorageIO`][redsun.storage.StorageIO] opens and describes it, and
[`OpenStore`][redsun.storage.OpenStore] is the handle bound to its lifetime.

### Structural subtyping

Conformance decided by the members a class has rather than by what it inherits
from. Presenters and views are validated against `@runtime_checkable`
protocols on the built instance, so a component never has to inherit from
redsun to satisfy one.

### View

The component holding a session's widgets. It declares signals and slots and
holds no behaviour of its own. Its constructor takes `(name)` alone.

### Virtual container

The session-wide object that is at once the signal bus, the provider registry
and the document-callback registry. Every component reaches the others through
it rather than holding a reference to them.

### Wiring

The declaration of which signal reaches which slot. It belongs to the
application, not to the components: a component declares its ports, and the
session says how they connect.
