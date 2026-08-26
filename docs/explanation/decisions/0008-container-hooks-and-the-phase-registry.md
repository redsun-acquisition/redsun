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

**Toolkit hook points are one generic protocol each, aliased per toolkit.**
What differs between toolkits is the objects, not the moments: Qt has a
`QApplication` and a main window, wx has `wx.App` and `wx.Frame`, Tk merges
both into one, a web frontend has no application object at all. So
`CreatesApplication`, `ConfiguresApplication` and `ConfiguresMainView` are
parameterised on the object and each toolkit supplies aliases, rather than
protocols of its own. There are three protocol names in total, forever, and a
plugin author learns three rather than three times the number of toolkits.

The variance is forced, not stylistic: `create_application` returns the
application so its variable is covariant, `configure_application` accepts one
so its variable is contravariant, and a single shared variable does not
compile. Contravariance also means a hook point is satisfied by a *wider*
parameter - a `configure_main_view` taking `QWidget` legitimately satisfies one
demanding a main window - which is correct and worth knowing when reading the
type-level tests.

Static checking is the whole point of the parameter, because runtime checking
cannot reach it: `isinstance` refuses a parameterised protocol, so a container
narrows to the bare form and a provider built for the wrong toolkit is only
caught when called. `tests/typing/qt_hook_aliases.py` pins what mypy sees.

**A provider implementing a hook point its container never calls is warned
about, not refused.** A container names the subset of `HOOK_PROTOCOLS` it calls
in `_hook_protocols`; the difference is what a provider implements in vain. A
provider serving several toolkits is legitimate, so this is not an error - but
it is inert, and silence is exactly what a typo'd method name looks like.
Implementing *nothing* the container calls still raises.

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

**A hook that only watches gets a signal, not a hook point.** A splash screen
naming the step in progress does not want to add work at a moment; it wants to
observe the sequence. Through the registry that is one registered phase per
label, each doing nothing but emit a string. `sig_phase_complete` carries the
name of each phase as it finishes, and a provider connects to it in
`configure_build` - so the opt-in is still configuration, not code. It lives on
`AppContainer` rather than on `VirtualContainer` because the bus is created
*by* the first phase and so could not report that phase.

This forces `__weakref__` into `AppContainer.__slots__`. psygnal keeps one
`SignalInstance` per owner and refers to that owner weakly, both in the
instance itself and in the `weakref.finalize` that drops its cache entry. Both
fall back to a strong reference when the owner cannot be weakly referenced, and
a class using `__slots__` cannot be unless `__weakref__` is among its slots.
The fallback is deliberate on psygnal's part - it keeps signals working for
owners that are neither hashable nor weak-referenceable - but its cost here is
that no container is ever collected: not the container, nor its devices,
presenters, views, bus or connections. An ordinary class never reaches this
path, because psygnal stores the `SignalInstance` as a plain attribute when the
owner has a `__dict__`; only a slotted owner does.

The rule generalises past this signal: **a `__slots__` class that owns a
psygnal `Signal` needs `__weakref__` in its slots.**

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
