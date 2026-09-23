# Build documentation

## Prerequisites

[Set up a development environment](setup.md).

## Build with Zensical

From the project root:

```bash
uv run tox -e docs
```

This builds the site, then runs `scripts/check_xrefs.py`, which reports every
cross-reference that resolves to nothing. `zensical build` alone passes with
such references, so prefer the `tox` environment:

```bash
uv run zensical build          # build only, no cross-reference check
```

The site lands in `site/`. Serve it locally with:

```bash
uv run zensical serve
```

The server listens on `http://localhost:8000` and rebuilds on every change.

## Troubleshooting

### Missing dependencies

```bash
uv sync --group docs
```

`uv run tox -e docs` installs them itself, from `uv.lock`.

### Port already in use

Pick another port:

```bash
uv run zensical serve --dev-addr localhost:8080
```

## Next steps

- [Run tests](run-tests.md)
- [Write documentation](write-docs.md)
