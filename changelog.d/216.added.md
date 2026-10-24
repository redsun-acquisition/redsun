`PlanProgress` is generic over the type of the values it reports, and `PlanProgress.update` returns its last update. `monitor_progress` returns a `PlanProgress[T]` for a `WatchableAsyncStatus[T]`.
