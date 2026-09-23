---
icon: lucide/book
---

# How to build the docs

## Prerequisites

[Set up a development environment](set-up-development.md).

## Build with Zensical

From the project root:

```bash
uv run tox -e docs
```

This builds the site, then runs `scripts/check_xrefs.py`, which reports every
cross-reference that resolves to nothing. `zensical build` alone passes with
such references, so prefer the `tox` environment. It installs what the docs
need by itself, from `uv.lock`.

Zensical lives in the `docs` dependency group, which `dev` does not include,
so a command running it directly names the group:

```bash
uv run --group docs zensical build     # build only, no cross-reference check
```

The site lands in `site/`. Serve it locally with:

```bash
uv run --group docs zensical serve
```

The server listens on `http://localhost:8000` and rebuilds on every change.

## Troubleshooting

### `zensical` is not found

`uv run zensical` without `--group docs` fails with
`Failed to spawn: zensical`. Add the flag, or install the group once:

```bash
uv sync --group dev --group docs
```

### Port already in use

Pick another port:

```bash
uv run --group docs zensical serve --dev-addr localhost:8080
```

## Next steps

- [Run tests](run-tests.md)
- [Write documentation](write-docs.md)
