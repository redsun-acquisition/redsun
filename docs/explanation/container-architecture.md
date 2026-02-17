# Container architecture

Redsun uses a **container-based Model-View-Presenter (MVP) architecture** to manage the lifecycle and dependencies of application components.

## Overview

At the core of Redsun is the [`AppContainer`][redsun.containers.container.AppContainer], which acts as the central registry and build system for all application components. Components are declared as class attributes and instantiated in a well-defined dependency order.

```mermaid
graph LR
    subgraph 1. Create infrastructure
        VirtualBus
        DI[DI Container]
    end

    subgraph 2. Build components
        Devices
        Presenters
        Views
    end

    Devices --> Presenters
    Presenters --> Views
    VirtualBus --> Presenters
    VirtualBus --> Views
    Presenters -.->|register providers| DI
    DI -.->|inject dependencies| Views
```

## The MVP pattern

Redsun follows the **Model-View-Presenter** pattern provided by [Sunflare]:

- **Model (Devices)**: hardware abstractions that implement Bluesky's device protocols. They represent the actual instruments being controlled.
- **View**: user interface components (currently Qt-based) that display data and capture user interactions.
- **Presenter**: business logic components that sit between models and views, coordinating device operations and updating the UI through the virtual bus.

This separation ensures that hardware drivers, UI components, and business logic can be developed and tested independently.

## Declarative component registration

Components are declared as annotated class attributes using the [`component()`][redsun.containers.components.component] field specifier:

```python
from redsun.containers import AppContainer, component

class MyApp(AppContainer):
    motor: MyMotor = component(layer="device", axis=["X", "Y"])
    ctrl: MyController = component(layer="presenter", gain=1.0)
    ui: MyView = component(layer="view")
```

The [`AppContainerMeta`][redsun.containers.container.AppContainerMeta] metaclass collects these declarations at class creation time, resolving type annotations to concrete component classes. This declarative approach allows the container to:

- validate component types at class creation time;
- inherit and override components from base classes;
- merge configuration from YAML files with inline keyword arguments.

## Configuration file support

Components can pull their keyword arguments from a YAML configuration file:
```python
from redsun.containers import AppContainer, component, config

class MyApp(AppContainer):
    cfg = config("app_config.yaml")
    motor: MyMotor = component(layer="device", from_config="motor")
```

The configuration file provides base keyword arguments that can be overridden by inline values in the [`component()`][redsun.containers.components.component] call. This allows the same application class to be reused across different setups by swapping configuration files.

## Build order

When [`build()`][redsun.containers.container.AppContainer.build] is called, the container instantiates components in a strict dependency order:

1. **VirtualBus** - the event-driven communication channel.
2. **DI container** - the dependency injection container, seeded with the application configuration.
3. **Devices** - hardware interfaces, each receiving their name and keyword arguments.
4. **Presenters** - business logic components, receiving the full device dictionary and virtual bus. Presenters that implement `IsProvider` register their providers in the DI container.
5. **Views** - UI components, receiving the virtual bus. Views that implement `IsInjectable` receive dependencies from the DI container.

## Communication

Components communicate through two mechanisms:

- **Virtual bus**: an event-driven publish/subscribe system provided by Sunflare. Presenters and views can emit and listen for signals without direct references to each other.
- **Dependency injection**: presenters can register providers in the DI container, and views can consume them. This allows views to access presenter-provided data without coupling to specific presenter implementations.

## Qt integration

The [`QtAppContainer`][redsun.containers.qt_container.QtAppContainer] extends [`AppContainer`][redsun.containers.container.AppContainer] with the full Qt lifecycle:

1. Creates the `QApplication` instance.
2. Calls [`build()`][redsun.containers.container.AppContainer.build] to instantiate all components.
3. Constructs the [`QtMainView`][redsun.view.qt.mainview.QtMainView] main window and docks all views.
4. Connects `VirtualAware` views to the virtual bus.
5. Starts the `psygnal` signal queue bridge for thread-safe signal delivery.
6. Shows the main window and enters the Qt event loop.

[sunflare]: https://redsun-acquisition.github.io/sunflare/
