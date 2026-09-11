# 3. Structural subtyping for presenters and views

Date: 2026-07-24

## Status

Accepted, superseded in part by
[11. Tolerating a component that fails to build](0011-tolerating-a-component-that-fails-to-build.md).

A presenter or view whose instance fails the protocol check is logged and
skipped there rather than re-raising. What remains in force is the dual gate
itself: the constructor's positional shape is checked at declaration or
discovery, protocol compliance on the built instance.

## Context

Redsun's wiring is protocol-based: components are recognized by what they
expose, not by what they inherit. Two defects undermined that promise for
the presenter and view layers.

**Static structural subtyping was broken by read-write protocol members.**
`PPresenter` declared `name: str` and `devices: Mapping[str, Device]` as
plain attributes; `PView` declared `name: str`. A plain protocol attribute
demands a *settable, invariantly typed* member from implementers, so (as
verified with mypy):

- a class exposing `name` as a read-only property failed the protocol
  ("expected settable variable, got read-only attribute") - even though
  ophyd-async's own `Device.name` is a read-only property;
- a class annotating `self.devices: dict[str, Device]` failed too, because
  read-write members are invariant and `dict` is not `Mapping`.

Every plausible duck-typed implementer therefore failed static checks;
nobody noticed because everything inherited the nominal ABCs.

**Runtime validation checked classes, where the information does not
exist.** `issubclass` is a `TypeError` for data-member protocols, so the
container hand-rolled `hasattr(cls, ...)` checks - on the *class*. Instance
attributes assigned in `__init__` (the normal style) are invisible there,
so structurally compliant non-ABC components were rejected at plugin
discovery. The check then papered over the container's nominal typing with
`ABC.register(cls)`.

A third wrinkle surfaced during the fix: a protocol's property members are
real descriptors, so a class inheriting the protocol *and* assigning
`self.name = ...` raises `AttributeError` at runtime (setter-less property).
The ABCs must therefore not inherit the protocols they satisfy.

## Decision

1. **Protocol data members are read-only properties.** `PPresenter.name`,
   `PPresenter.devices`, and `PView.name` are declared as `@property` in the
   protocols. The framework only ever reads them, so read-only is the true
   contract. Implementers may use plain instance attributes, class
   attributes, or properties, and covariant types (`dict` for `Mapping`)
   are accepted.
2. **The ABCs do not inherit the protocols.** `Presenter(ABC)` and
   `View(ABC)` satisfy `PPresenter`/`PView` structurally, exactly like any
   other implementer - inheritance would shadow instance attributes with
   the protocols' property descriptors.
3. **Validation is a dual gate.** The parts of the contract are checked
   where they are actually knowable:

   - *Class level - constructor signature.* The container instantiates
     components as `cls(*positionals, **config_kwargs)`, so the knowable
     class-level contract is purely positional. `expects_positionals`
     (`inspect`-based) verifies the leading positional parameters are
     exactly `("name", "devices")` for presenters and `("name",)` for
     views, that any further positional-or-keyword parameters carry
     defaults, that `*args` is absent, and that the container's positional
     call binds. Keyword arguments are deliberately unvalidated - the
     container has no control over them. This gate runs at component
     wrapper creation (declarative path, at class definition time) and at
     plugin discovery (config path, log-and-skip).
   - *Instance level - protocol compliance.* `_PresenterComponent.build` /
     `_ViewComponent.build` run `isinstance(instance, PPresenter/PView)`
     after construction and raise `TypeError` on failure - instance
     attributes assigned in `__init__` are only visible here. This sits on
     the correct side of the "presenter/view build failures re-raise"
     invariant.

   The old class-level hasattr screen and the `ABC.register` hack are gone.
4. **The container is typed against the protocols.** Components hold
   constructors as `Callable[..., PPresenter]` / `Callable[..., PView]`
   (`type[Protocol]` is not callable for type checkers), and
   `AppContainer.presenters` / `.views` return `dict[str, PPresenter]` /
   `dict[str, PView]`. Devices remain nominal (`ophyd_async.core.Device`).

## Consequences

- Structural implementers - property-based, attribute-based, or Qt widgets
  like `QtView` - now pass both static and runtime checks; the
  `type: ignore` previously needed for `_ViewComponent(QtView-subclass)`
  is deleted.
- Components with a wrong constructor shape fail **at declaration or
  discovery time**; components whose instances miss protocol members fail
  **at build time** - both with a loud `TypeError` naming the problem,
  instead of being silently skipped or slipping through the old
  class-level attribute screen.
- Breaking: `AppContainer.presenters`/`views` are typed against the
  protocols; code annotated against the ABCs keeps working at runtime but
  should re-annotate. Classes that explicitly inherited `PPresenter`/`PView`
  while assigning instance attributes must drop the inheritance (it was
  latently broken at runtime already).
- Regression tests pin: property-based and dict-based implementers
  (static + runtime), ABC structural compliance, duck components building
  without the ABC, and non-compliant components raising at build.
