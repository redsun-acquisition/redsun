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

Three facts about a constructor shape the answer. A presenter's or view's
annotated parameter can come from the file or from the session: the file
wins when it gives the key, and otherwise the session looks the parameter's
type up in what it holds. A device is given nothing by type, because the
build passes it the keys of its entry, its services' prefixes and its
`path_provider`, by that name. And which types a session holds depends on
its providers, which a description of one plugin can't see.

## Decision

`redsun describe` sorts each constructor parameter, then generates one
`pydantic` model per entry with `create_model`, based on the session file's
own model of that group's entries (`DeviceEntry`, `PresenterEntry`,
`ViewEntry`). The model's schema is what the command prints, and
`redsun check` validates an entry's values with the same model.

A presenter's or view's parameter is sorted by its type:

- the session fills it when its type is `DevicesOf[...]`, a compute executor,
  a type the session holds itself (`Settings`, `SessionConfig`,
  `DeviceMapping`, `SessionPathProvider`, `CatalogAddress`, the callback
  catalogue), or any type `pydantic` can't write a schema of, such as a
  protocol or another component's class;
- every other parameter is a key of the file. It is required when it has no
  default, unless its type is one of its own that a provider can share: a
  `pydantic` model, a dataclass, a `TypedDict` or a `NewType`. Such a key is
  listed among what the session fills as well, and the file may give it. A
  key written `X | None` without a default is given `None`, as the build
  gives it when nothing provides `X`.

Every parameter of a device is a key of the file, except `path_provider`,
which the session fills by its name. So a model type is a required key like
any other, and a required parameter whose type has no schema, such as
`DeviceMapping`, makes the device fail, since no file can give it.
`X | None` is the exception, because the file may give `null`:

```python
class MyMotor(Device):
    def __init__(
        self, prefix: str, path_provider: PathProvider, calibration: Calibration,
        name: str = "",
    ) -> None: ...
```

```text
devices/motor (mylab.devices:MyMotor)
  prefix: string, required, or from a service
  calibration: Calibration, required, or from a service
  the session fills: path_provider (ophyd_async.core.PathProvider)
```

A key whose schema `pydantic` fails to write, such as one whose type names
a forward reference it can't resolve, is reported as a `parameter` problem
and takes any value, so the rest of the class is still described.

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

Two other ways of writing the schema were weighed against the one taken:

```python
# taken: one model per entry, based on the group's own entry model
model = create_model("MyControllerEntry", __base__=PresenterEntry, step=(float, 1.0))
model.model_json_schema()  # what redsun describe prints
model.model_validate(entry)  # what redsun check runs
```

```python
# weighed: one TypeAdapter per parameter, the object put together by our own code
for name, annotation in annotations.items():
    part = TypeAdapter(annotation).json_schema()
    defs.update(part.pop("$defs", {}))  # two classes named Calibration overwrite each other
    properties[name] = part
```

```python
# weighed: the plan spec, which reads a plan's parameters into widget descriptions
spec = create_plan_spec(MyController.__init__, devices)
```

The second would have had to merge the `$defs` of every parameter, where two
parameters can define the same name, and `create_model` does that already.
The third would have tied components to code built for plan widgets, and it
needs a session's devices before it can describe anything.

The `required` rule decided between two mistakes. Marking a model-type key
required would make a form demand a value that a provider of the session
fills, and a value the user typed to get past the form would then replace
the provider's without a word, because the file's key always wins. Leaving
it optional means a session with no such provider stops at build with the
key named. The second mistake can be seen, so it is the one kept. A plain
`str` or `float` is never shared by a provider, so it stays required.

When a presenter or view leaves out such a plain key, the whole session
stops. The build fills these components by type, and when nothing provides
a `str` it stops instead of skipping the component. So `redsun check`
reports the stop as a `session` problem at the entry's path, besides
marking the component `failed`, and lists every entry that would stop the
build, where the build stops at the first:

```text
problems:
  presenters.ctrl: 'ctrl' asks for 'label' (str), which nothing in the session provides. A component names the values it needs, and the session is not one of them.
components:
  failed     presenters ctrl   (mylab:controller, mylab.controllers:MyController) - missing 'label'
```

Saying so only in the component's `reason` was weighed too. A tool reading
the report would then have to parse that text to learn that the session
never starts, while a `session` problem already means that for a file that
can't be read.

## Consequences

- `redsun describe` prints the schema, and `redsun check` reports a value
  that breaks a constructor's type or limits as a `value` problem.
- `redsun check` tells a session that stops at build from one that runs
  without a component: only the first has a `session` problem.
- The build itself still passes the file's values on unchecked, so a file
  that builds today still builds.
- The same model is ready for later work: the build checking values, a
  schema shipped in a plugin's wheel, and describing stacks, services and
  providers.
