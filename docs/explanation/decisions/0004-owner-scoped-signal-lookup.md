# 4. Owner-scoped signal lookup

Date: 2026-07-24

## Status

Accepted

## Context

The `VirtualContainer` signal registry is two-level - keyed by owner name
first, then by signal name (`container.signals[owner][signal]`) - precisely
because different components may expose signals with the same name and the
owner name is what discerns them. `find_signals`, however, only searched by
signal name across every cache and silently returned the first match, so
two components exposing e.g. `sig_new_frame` could not be told apart by a
consumer using the helper. The callback registry has the same shape
awareness (keys default to the owner's name); the signal helper should be
aligned with it.

## Decision

`find_signals` gains an optional `owner` keyword. When given, the lookup is
restricted to that component's cache (its `name`, or the alias used at
registration); an unknown owner yields an empty result, consistent with the
existing omit-missing semantics. When omitted, the legacy first-match scan
across all caches is preserved - convenient when a signal name is known to
be unique, ambiguous otherwise.

As a companion convention, signal attributes follow standard Python naming:
`sig_snake_case` (the `sig_` prefix is a readability aid and may be dropped
by component authors), replacing the previous `sigCamelCase` style.
`StoragePresenter` now wires `sig_pre_launch_notify` / `sig_plan_done`, and
`DescriptorTreeView` exposes `sig_property_changed`.

## Consequences

- Consumers that must disambiguate same-named signals pass the owner name;
  redsun-mimir's presenters and views should adopt the owner-scoped form in
  their refactor and rename their signals to `sig_snake_case` - until then,
  mimir's `sigCamelCase` emitters will not match redsun's renamed
  `StoragePresenter` wiring.
- The rename is breaking for any consumer that looked up the old
  `sigCamelCase` keys.
