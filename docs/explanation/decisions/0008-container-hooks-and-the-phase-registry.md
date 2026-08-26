# 8. Container hooks and the build phase registry

Date: 2026-08-26

## Status

Accepted

## Context

A session may need to adjust the application container itself, rather than any
one component. The case that forced the question is theming: a bundle that
embeds a third-party widget brings that widget's own stylesheet, and confining
it to one widget makes the window look like two applications stitched together.
Applying it to the whole application has to happen before any view is built,
which is inside `build`, where no component has a say.

`build` was a straight-line body, so there was no way to add a step to it and
no name for any point inside it. The only extension points were `wire`, which
runs at one fixed place, and overriding `build` in a subclass, which does not
compose: two packages that both want to adjust the build cannot both be the
subclass.

Whatever mechanism was chosen had to work from a configuration file as well as
from Python, because a session assembled entirely from YAML is a first-class
way to run redsun and must not lose a capability that a container class has.

## Decision

**The build sequence is a registry, not a straight-line body.** `AppContainer`
holds `_phases`, an insertion-ordered mapping of name to bound method, built in
`__init__`. `build` iterates it. The shape is `RunEngine._command_registry` from
bluesky, already a dependency: a dict of bound methods populated in `__init__`
and read publicly through a property.

Bound methods rather than a module-level table of names, for two reasons.
Unbound references would call the base implementation even on a subclass that
overrides a phase, losing the override; binding through the instance keeps it.
And a string-keyed `getattr` is invisible to a type checker, so a mistyped
phase name would need a runtime test to catch, where a bound method is reported
directly.

**Insertion is public, permutation is not.** `register_phase(name, phase,
after=...)` adds a step; `unregister_phase` removes one; `phases` reports the
order. The RunEngine's registry is order-free, because a plan's message stream
decides sequence and registering a command changes no order. Here the order is
the semantic content, so:

- `after` is required. There is no meaningful default position.
- The built-in phases cannot be removed or reordered. Four orderings are
  load-bearing - the bus before everything, devices before presenters, every
  component before wiring, every provider registration before any injection -
  and they stay guarantees rather than hopes.
- Registration is only legal before `build`, mirroring the storage layer's rule
  that `register` is legal only before `open`.

**Hook providers are plain objects, checked structurally.** A provider
implements `ConfiguresBuild` to adjust the sequence, `HasShutdown` to undo what
it did, or both; each is checked independently with `isinstance`, which is the
idiom `build` already uses for `IsProvider` and `IsInjectable`. There is no base
class to inherit and no protocol that demands methods a provider does not want,
so a class defining one method is a complete provider.

**A session names providers in either of two places, and both feed one list.** A
configuration file names them by dotted path, since YAML cannot hold a class; a
container class lists instances, since an author writing Python already holds
the provider. The two concatenate, class-level first. Neither overrides the
other: silent override would decide behaviour by which of two files the reader
is not looking at.

**Teardown is symmetric and owned by the container.** `shutdown` walks the
providers in reverse, after the presenters, logging failures rather than
raising - the opposite of the setup rule, because a failing teardown happens
while the application is already going down and must not block the rest. The
container additionally restores the phase sequence it captured before the hooks
ran, so a container built twice does not accumulate phases and a hook author
does not have to hold a container reference to undo a registration.

**Failures during setup raise.** A device that fails to build is logged and
skipped, because missing hardware must not abort a session. A hook that does
not resolve is a typo in a configuration file, not a missing instrument. A
provider satisfying none of the protocols its container calls raises for the
same reason: it would silently do nothing.

## Consequences

- A bundle can ship application-wide behaviour as one class and a session opts
  in with one configuration entry, without subclassing the container.
- Two packages can each contribute to the same session, which a subclass-based
  extension point cannot express.
- `build` has a vocabulary: every step has a name a hook can address, and the
  names appear in the debug log.
- A phase registered by hand survives a rebuild; a phase registered by a hook
  does not. That asymmetry is deliberate - the container undoes what it caused.
- `hooks` is declared as a `Sequence` and normalised to a tuple, so a class body
  can use a tuple and avoid the mutable-class-attribute lint that a list form
  would trip in every downstream package.
- The protocols a container calls are a class attribute, so a container for
  another toolkit extends the set rather than redefining the check.
- Nothing is configurable that would break the four load-bearing orderings: the
  sequence is data so that hooks can address it, not so that a session file can
  rewrite it.
