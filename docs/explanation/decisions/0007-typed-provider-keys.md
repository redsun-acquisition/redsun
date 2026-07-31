# 7. Typed provider keys

Date: 2026-07-31

## Status

Accepted

## Context

Objects shared between components go through the virtual container. Until now
the sharing surface was the container's dynamic attributes:

```python
container.path_provider = providers.Object(self._provider)  # producer
provider = container.path_provider()  # consumer
```

`VirtualContainer` subclasses `DynamicContainer`, so attribute access on it
returns `Any`. Both halves of that exchange are unchecked. The consumer's
annotation is a promise, not a check; the attribute name is a string agreed by
convention; and a consumer whose producer is absent gets `AttributeError`,
which is indistinguishable from a typo.

`dependency-injector` is properly generic. `providers.Object[T]`,
`providers.Factory[T]` and `providers.Dependency[T]` all carry their type
through to the call, so the type information is available and `DynamicContainer`
is what discards it. The fix is to use the library as intended rather than to
add an abstraction: a hand-rolled typed key would be `providers.Dependency`
with a worse name.

Two mechanical facts shaped the result.

`Dependency(instance_of=...)` gives a runtime `isinstance` check alongside the
static parameter, which is what makes the key self-describing.

`Dependency.override()` mutates the key object itself, and a key is a
module-level constant, so a binding made through it is process-global. Two
containers in one process would clobber each other's bindings, which is the
defect `VirtualContainer.__init__` already avoids by scoping its signal and
callback registries per instance. Bindings therefore cannot live on the key.

## Decision

A shared object is identified by a **typed key**, a `providers.Dependency[T]`
exported as `ProviderKey[T]`, and bound per container:

```python
PATH_PROVIDER = dip.Dependency(instance_of=SessionPathProvider)

container.provide(PATH_PROVIDER, self._provider)  # producer
provider = container.require(PATH_PROVIDER)  # consumer
maybe = container.try_require(PATH_PROVIDER)  # optional collaborator
```

The key is a name, not storage. `VirtualContainer` holds the bindings in its
own mapping and never calls `Dependency.override`.

`provide` enforces `instance_of` where the value is bound, so a wrong value is
blamed on the component that supplied it. `require` raises `KeyError` naming the
key; `try_require` returns `None`, which is how an application states that a
collaborator is optional rather than expressing it as silence.

A key lives beside the type it identifies, in the package that owns that type,
and is exported from it. There is no central key module: a plugin defines its
own keys in its own package, and no plugin has to be listed anywhere for its
keys to work.

## Consequences

Provider exchange becomes statically checked. `container.require(PATH_PROVIDER)`
is a `SessionPathProvider` to a type checker, and passing the wrong value to
`provide` is a type error before it is a runtime one.

Absence becomes expressible. `try_require` returning `None` distinguishes an
optional collaborator from a typo, where the dynamic attribute made both an
`AttributeError`.

`container.path_provider` is gone. Any component reading it must move to
`container.require(PATH_PROVIDER)`, which is a breaking change for out-of-tree
consumers.

The dynamic-attribute mechanism still exists on `DynamicContainer` and is not
removed. Nothing forces an existing provider onto keys, but new providers should
use them, and untyped attribute registration should not be added.

dishka was considered as an alternative and rejected. It resolves dependencies
by type at a composition root, which inverts this build model: redsun constructs
plugin instances discovered from configuration at runtime and lets them register
what they own. Type keys also collide with the plugin model, where two cameras
or two presenters of one class are normal and the configuration key is the
identity. The migration would break `register_providers` and
`inject_dependencies`, which are the public plugin API, in exchange for
generics that `dependency-injector` already provides.
