# Build documentation

This guide covers how to build the Redsun documentation locally.

## Prerequisites

Make sure you have [installed `redsun` with development dependencies](installation.md#install-development-dependencies).

## Build with Zensical

Build the documentation from the project root:

```bash
uv run zensical build
```

The built documentation will be in the `site/` directory. You can serve the documentation locally via:

```bash
uv run zensical serve
```

This starts a local server at `http://localhost:8000` and automatically rebuilds when you make changes.

## Troubleshooting

### Missing dependencies

If you get errors about missing dependencies:

```bash
uv sync
```

### Port already in use

If port 8000 is already in use, specify a different port:

```bash
uv run zensical serve --dev-addr localhost:8080
```

## Next steps

- Learn how to [run tests](run-tests.md)
- Read about [Redsun's architecture](../explanation/container-architecture.md)
