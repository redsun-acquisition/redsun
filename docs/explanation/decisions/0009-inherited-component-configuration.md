# 9. Inherited and layered component configuration

Date: 2026-08-28

## Status

Accepted

## Context

Two sessions of the same instrument differ in their hardware and in almost
nothing else. A simulated microscope and the real one declare the same
presenters, the same views and the same wiring; only the devices and the
configuration change. Written as two container classes, everything but the
devices is duplicated, and the duplication is the part that carries the
application's structure.

Python already has the mechanism for that: a base class holding the shared
declarations, subclassed once per session. It did not work here, for two
reasons that both come from `from_config` being resolved as the class body is
read.

A base class has no configuration file of its own - the file is the thing that
differs - so every `from_config` field in it raised at class creation:
`Component field 'ui' in InstrumentApp has from_config set but no config path
was provided`. Giving the base a file instead makes the resolution happen
against that file, and `__init_subclass__` then copies the built wrappers into
the subclass, so a subclass naming its own `config` inherits the base's keyword
arguments and silently ignores its own file.

Both are consequences of the same thing: the fields were consumed at class
creation and not kept, so nothing was left for a subclass to re-resolve.

Sharing the declarations is only half of it. `config` named a single file and a
subclass replaced its base's rather than adding to it, so a subclass had to
restate every section its base's file carried. The duplication would move from
the Python to the YAML rather than going away.

The objection to layering files is that a reader would have to consult two of
them to know one component's arguments. That objection is real, and it is the
same one that made [container hooks](0008-container-hooks-and-the-phase-registry.md)
refuse a silent override between two sources. It is not the same situation. A
hook override is invisible: two files name the same hook point and nothing in
either says which wins. A layered configuration is declared at the class that
does the layering - `class Simulation(InstrumentApp, config="simulation.yaml")`
reads as "this session, on top of what InstrumentApp set up" - and the order is the
class hierarchy, which the reader is already holding.

## Decision

**The declared fields outlive class creation.** `AppContainer._component_fields`
records every `declare_*` field a container and its bases declared, keyed by
attribute name. It is accumulated the way the component wrappers already are:
bases first, then the class's own body.

**Every class resolves the whole inherited set against its own files.**
`__init_subclass__` no longer resolves only the fields written in that body; it
resolves everything in `_component_fields`. A subclass therefore rebuilds the
wrappers it inherited, reading its own configuration.

**A missing configuration file is refused at construction, not at class
creation.** A base class exists to be subclassed, and the subclass is where
`config` is named, so a class body cannot know whether a file will arrive. The
`TypeError` moves to `AppContainer.__init__`, and names every field that asked
for a section rather than the first one reached.

Resolution stays at class creation for a class that has a file. It is what lets
a type checker read a component's type off the class body, and moving it to
build time would buy nothing that the subclass rule does not already give.

**`_config_paths` is a tuple, and a subclass appends to it.** `config` accepts
one path or a sequence of them, and what a class declares is read *after* what
its bases declared. A subclass does not replace its base's file; it lays its own
over the top.

**Files merge as mappings, recursively.** `merge_config` takes a key from the
later file unless both values are mappings, which merge in turn. A list or a
scalar is replaced rather than combined, because there is no combination of two
lists that is right more often than it is wrong.

**A component entry is the exception: it is replaced whole.** Under `devices`,
`presenters` and `views` the section still merges by component name, so an
overlay adds components and leaves alone the ones it does not mention - but a
component it *does* name is taken from it entirely. Those entries are not a
tree of settings; they are the keyword arguments of `cls(name, **kwargs)`.
Assembling one constructor call from two files is how a session ends up running
with an argument nobody reading its file can see, and this framework drives
stages and cameras. One file owns one component's arguments, and a reader finds
them by looking at the last file that names it and stopping.

The hazard is not hypothetical. Two sessions of one instrument routinely give
the same component name to different classes - a mock light source and a real
one - so merged keyword arguments would reach two different constructors and
fail, if they failed at all, at build time naming the component but not the
file that contributed the key.

**Required keys are checked on the merged result, not on each file.** A file
that sits under another is a fragment - it has no reason to carry
`schema_version` or `frontend`, which belong to the session rather than to the
components. `_read_yaml` reads a file without judging it, and `_load_yaml`
validates once, after the merge, naming every file that took part.

**Two files may not disagree about what kind of session this is.**
`schema_version` and `frontend` name the session's identity rather than its
content, so a later file giving a different value is a contradiction rather
than an override, and raises. Restating an identical value is legal. Everything
else, `name` included, follows the ordinary rule that the later file wins -
naming the session per layer is the point of layering it.

`frontend` earns the rule twice over: on a declarative container it is already
inert, since the class is `QtAppContainer` whatever the file says. An overlay
flipping it would leave `container.config["frontend"]` reporting a toolkit the
container is not running, and nothing would say so.

## Consequences

- A base class can carry the presenters, views, hooks and `wire` that two
  sessions share, with each subclass supplying only its devices and the file
  that differs; a file common to both sits under the base.
- A class that previously failed at import now fails when constructed. The
  message is the same and names more; the timing is not.
- A configuration file is no longer necessarily a whole session. A file naming
  only a `presenters` section is legal as long as something under it supplies
  what `AppConfig` requires.
- The order is the class hierarchy, so a reader who wants a component's
  arguments reads the files from the base down. `_config_paths` reports that
  order. Every base contributes, and a file reached twice through the hierarchy
  is read once.
- The files a container read, and every component one file took from another,
  are logged at debug level, so an investigation into an unexpected keyword
  argument starts from the layer chain rather than from a guess.
- **An overlay naming a component restates all of its arguments.** That is the
  cost of the rule, and it is the one that buys back a reader's ability to know
  a component's arguments from one place. Where two sessions genuinely share a
  component, it belongs in the file underneath and the overlay says nothing.
- A key whose value is a list cannot be extended by an overlay, only replaced.
  An overlay wanting to add one axis to three restates all four.
- An inherited field whose section is missing from the merged configuration
  falls back to its inline keyword arguments with a warning, exactly as a
  directly declared one does. Treating inheritance as a stronger statement of
  intent, and raising instead, stays available as a later change.
- Nothing changes for a container naming a single file, which is still what
  `AppContainer.from_config` builds and what most sessions are.
