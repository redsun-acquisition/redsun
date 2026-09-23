# 14. Typed session files and plugin manifests

Date: 2026-09-23

## Status

Accepted.

## Context

A session file and a plugin manifest were read with `yaml.safe_load` into
plain mappings. `TypedDict`s documented their shape without enforcing it, and
checks were added by hand where a mistake had been made: unknown `storage`
keys, the shape of a wiring rule or a hook entry, the transport. Each check
raised on the first problem it found, with its own exception type, some at
load and some at build. A misspelled key elsewhere was read as its default,
or reached a component's constructor, where a device that fails to build is
logged and skipped. A manifest was not read until a session named one of its
entries, so a mistake in it surfaced only when a user hit it.

## Decision

1. Both file kinds are `pydantic` models: `SessionFile` in
   `redsun.containers._config` and `PluginManifest` in
   `redsun.containers._manifest`. Every model refuses unknown keys, except a
   component entry, whose other keys are the component's constructor
   keywords.
2. Layering is unchanged: files are read and merged as mappings, a later
   file owning a component entry whole and the identity keys having to agree.
   Validation runs once, on the merged result, so a layered file may be a
   fragment. The container keeps the mapping it validated, not a copy of the
   model, so entries a YAML anchor shares stay one object.
3. A class path is validated as text, `module:ClassName`, and imported only
   when a session uses it, so reading a manifest imports no plugin code.
4. A session file that does not validate raises `ConfigurationError`, a
   `ValueError` listing every problem as `section.key: what`. Wording that
   named the problem well is kept as the validators' messages.
5. Every installed manifest is validated when a session first looks one up.
   One that does not validate is logged with every problem and left out
   whole.
6. The JSON schema of each file kind is published with the documentation,
   describing a file as written, so an editor checks one as it is typed.
7. The models, their validators and their helpers live in private modules and
   are not exported, so their names carry no leading underscore.

## Consequences

A mistake in a session file is reported before anything is built, all at
once, with its location. Code catching the `TypeError`, `KeyError` or
`WiringError` a malformed file raised before catches `ConfigurationError`
instead.

A container class whose file does not validate fails when it is constructed,
or when it is created if it declares `from_config` fields, rather than
falling back to defaults.

`pydantic` is a declared dependency. It was already installed and imported
through `ophyd-async`.

The model and the file differ in two places: the model holds the transport
beside the sections and the hook entries as a list of groups. The published
schema is rewritten to the file's shape, and an error inside a hook entry is
located by its hook points.
