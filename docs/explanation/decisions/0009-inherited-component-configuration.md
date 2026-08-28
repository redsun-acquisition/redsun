# 9. Inherited component configuration

Date: 2026-08-28

## Status

Accepted

## Context

Two sessions of the same instrument differ in their hardware and in almost
nothing else. A simulated microscope and the real one declare the same
presenters, the same views and the same wiring; only the devices and the
configuration file change. Written as two container classes, everything but the
devices is duplicated, and the duplication is the part that carries the
application's structure.

Python already has the mechanism for that: a base class holding the shared
declarations, subclassed once per session. It did not work here, for two
reasons that both come from `from_config` being resolved as the class body is
read.

A base class has no configuration file of its own - the file is the thing that
differs - so every `from_config` field in it raised at class creation:
`Component field 'img_widget' in MimirBase has from_config set but no config
path was provided`. Giving the base a file instead makes the resolution happen
against that file, and `__init_subclass__` then copies the built wrappers into
the subclass, so a subclass naming its own `config` inherits the base's
keyword arguments and silently ignores its own file.

Both are consequences of the same thing: the fields were consumed at class
creation and not kept, so nothing was left for a subclass to re-resolve.

## Decision

**The declared fields outlive class creation.** `AppContainer._component_fields`
records every `declare_*` field a container and its bases declared, keyed by
attribute name. It is accumulated the way the component wrappers already are:
bases first, then the class's own body.

**Every class resolves the whole inherited set against its own file.**
`__init_subclass__` no longer resolves only the fields written in that body; it
resolves everything in `_component_fields` against that class's `_config_path`.
A subclass therefore rebuilds the wrappers it inherited, reading its own
configuration, and two subclasses of one base read two different files.

**A missing configuration file is refused at construction, not at class
creation.** A base class exists to be subclassed, and the subclass is where
`config` is named, so a class body cannot know whether a file will arrive. The
`TypeError` moves to `AppContainer.__init__`, and names every field that asked
for a section rather than the first one reached.

Resolution stays at class creation for a class that has a file. It is what lets
a type checker read a component's type off the class body, and moving it to
build time would buy nothing that the subclass rule does not already give.

## Consequences

- A base class can carry the presenters, views, hooks and `wire` that two
  sessions share, with each subclass supplying only its devices and its file.
- A class that today fails at import now fails when constructed. The message is
  the same and names more; the timing is not.
- **The subclass's file must be complete.** `config` names one path and a
  subclass replaces rather than merges, so a file must carry a section for every
  field its class inherits, and a base's file contributes nothing to a
  subclass. Sharing the declarations does not share the configuration.
- Layering configuration files - a common one under a per-session one - would
  close that gap and is deliberately not decided here: merging two files makes a
  reader consult both to know one component's arguments, which is the objection
  that made [container hooks](0008-container-hooks-and-the-phase-registry.md)
  refuse a silent override.
- An inherited field whose section is missing from the subclass's file falls
  back to its inline keyword arguments with a warning, exactly as a directly
  declared one does. Treating inheritance as a stronger statement of intent, and
  raising instead, stays available as a later change.
