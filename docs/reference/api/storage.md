# Storage

Design rationale: [Session storage](../../explanation/storage.md) and
[ADR 0002](../../explanation/decisions/0002-storage-dual-context-redesign.md).

## Storage lifecycle

::: redsun.storage.BaseStorage

::: redsun.storage.FrameSink

::: redsun.storage.StreamSpec

::: redsun.storage.StoreStateError

## Backend protocols

::: redsun.storage.SinkFactory

::: redsun.storage.StorageIO

::: redsun.storage.OpenStore

## Path providing

::: redsun.storage.SessionPathProvider

::: redsun.storage.PathSignals

::: redsun.storage.PATH_PROVIDER

## Registry

::: redsun.storage
    options:
      members:
        - register_storage
        - get_storage
        - reset_group
        - clear_registry
