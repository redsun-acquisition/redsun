# 12. Collaborators arrive in `setup`

Date: 2026-09-12

## Status

Accepted, and applied to `redsun.experimental` only. The supported container
keeps `register_providers` and `inject_dependencies`.

## Context

In the experimental session a component takes what it needs as constructor
parameters, and a value one component shares is registered while its owner is
constructed. A component taking that value therefore has to be built after its
owner, so the session computes a build order: the types each constructor asks
for, a topological sort of each layer, a refusal when two components need each
other, and a refusal when a component reaches into a layer built after its own.

That order cannot answer a question about the session as a whole, because a
component may be part of its own answer. Such values are live views instead:
they are handed over at construction and raise `SessionNotBuilt` when read
before the build is sealed. A component has to hold one and read it later, and
the only way to learn that rule is to hit the exception.

Both come from the same cause. A constructor is the only place a component
receives anything, so the session has to make every value available before the
component exists.

## Decision

A component may define `setup`, a synchronous method the session calls once
every presenter and view has been constructed. Its parameters are filled from
the store the way a constructor's are, and it runs in a build step of its own,
`setup_components`, between `build_views` and `seal`.

A constructor keeps taking the component's name, its configuration, and what
the session holds before any component exists. Everything owned by another
component moves to `setup`.

A `setup` that cannot run is reported and changes nothing else: the component
keeps its place in `presenters` and `views`, its wiring, and whatever its
constructor made. What `setup` was going to assign is missing where it is used.
The closing summary names it, beside the components that failed to build.

An `async def setup` is refused at declaration, since the session calls it
without awaiting.

## Consequences

A constructor no longer names everything a component needs; `setup` does, one
method below it. Between the two, anything owned by another component is
missing, and only the session calls a component in that window.

The build order stops being a consequence of who shares what, so the machinery
that computes it can go: the dependency edges, the per-layer sort, the cycle
refusal, and the readiness gate on the live views. Two components may then take
each other's values, which no longer forms a cycle.

Components are shut down in the reverse of construction order, which within a
layer becomes declaration order rather than dependency order. A `shutdown` may
therefore run after a sibling whose value it took, so it must not use what
`setup` handed it.

A value shared with `provides` is read once, when its owner is constructed, so
it cannot depend on state the owner's own `setup` assigns.
