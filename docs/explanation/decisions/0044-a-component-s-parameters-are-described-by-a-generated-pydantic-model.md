# 44. A component's parameters are described by a generated `pydantic` model

Date: 2026-11-27

## Status

Accepted

## Context

A tool that writes session files for people who don't write Python, such as
a desktop manager drawing a form for each component, needs to know which
keys an entry takes. Until now only a build could tell. The session read a
constructor with `inspect.signature` and filled what it could by type, and
which parameters it filled was decided by private functions. Limits written
with `annotated-types` were read for plan parameters only (ADR 26), and a
constructor keyword had no place for a title, a description or a unit.

Two facts about a constructor shape the answer. Any annotated parameter can
come from the file or from the session: the file wins when it gives the key,
and otherwise the session looks the parameter's type up in what it holds. And
which types a session holds depends on its providers, which a description of
one plugin can't see.

## Decision

`redsun describe` sorts each constructor parameter, then generates one
`pydantic` model per entry with `create_model`, based on the session file's
own model of that group's entries (`DeviceEntry`, `PresenterEntry`,
`ViewEntry`). The model's schema is what the command prints, and
`redsun check` validates an entry's values with the same model.

A parameter is sorted by its type:

- the session fills it when its type is `DevicesOf[...]`, a compute executor,
  a type the session holds itself (`Settings`, `SessionConfig`,
  `DeviceMapping`, `SessionPathProvider`, `CatalogAddress`, the callback
  catalogue), or any type `pydantic` can't write a schema of, such as a
  protocol or another component's class;
- every other parameter is a key of the file. It is required when it has no
  default, unless its type is one of its own that a provider can share: a
  `pydantic` model, a dataclass, a `TypedDict` or a `NewType`. Such a key is
  listed among what the session fills as well, and the file may give it.

A parameter's text and unit are written with `pydantic`'s `Field` inside
`Annotated`, beside the `annotated-types` limits:

```python
# before
def __init__(self, name: str, *, step: float = 1.0) -> None: ...
```

```json
{"step": {"type": "number", "default": 1.0, "title": "Step"}}
```

```python
# after
def __init__(
    self,
    name: str,
    *,
    step: Annotated[
        float,
        Gt(0),
        Field(title="Step", description="How far one press moves.",
              json_schema_extra={"unit": "um"}),
    ] = 1.0,
) -> None: ...
```

```json
{"step": {"type": "number", "default": 1.0, "exclusiveMinimum": 0,
          "title": "Step", "description": "How far one press moves.", "unit": "um"}}
```

Two other ways were weighed. One `TypeAdapter` per parameter, with the
object's schema put together by our own code, would have had to merge the
`$defs` of every parameter, where two parameters can define the same name;
`create_model` does that already. Reusing the plan spec's `ParamDescription`
would have tied components to code built for plan widgets, devices and
actions.

The `required` rule decided between two mistakes. Marking a model-type key
required would make a form demand a value that a provider of the session
fills, and a value the user typed to get past the form would then replace
the provider's without a word, because the file's key always wins. Leaving
it optional means a session with no such provider stops at build with the
key named. The second mistake can be seen, so it is the one kept. A plain
`str` or `float` is never shared by a provider, so it stays required.

## Consequences

- `redsun describe` prints the schema, and `redsun check` reports a value
  that breaks a constructor's type or limits as a `value` problem.
- The build itself still passes the file's values on unchecked, so a file
  that builds today still builds.
- The same model is ready for later work: the build checking values, a
  schema shipped in a plugin's wheel, and describing stacks, services and
  providers.
