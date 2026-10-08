---
icon: lucide/target
---

# Why redsun exists

Acquiring scientific data means controlling many devices, coordinating
measurements, and managing the data and metadata they produce. The [Bluesky]
ecosystem gives you a common way to talk to hardware and a model for the data,
but turning them into a complete application with a usable interface is still
hard work.

`redsun` fills that gap. It's a toolkit for building your own acquisition
software out of small, separate [components](glossary.md#component) that work
together by sending each other signals.

## SDK, components and application

`redsun` is both the software development kit (SDK) you write components with
and the application shell that runs them. Step through the diagram to follow a
component from your code to the running application, and point at a shape to
read more:

```d2 title="From your components to an application"
...@diagrams/style
direction: down
sdk: "redsun as SDK" {
  class: layer
  tooltip: The patterns you write components in: devices, presenters and views, and the signals, slots and shared values they exchange, so every package is written the same way.
}
components: "your components\nin your code or a plugin" {class: hidden}
session: "a session\nclass or session file" {class: hidden}
shell: "redsun as application shell" {class: hidden}
app: "your application\nwindow, plans, data" {class: hidden}
sdk -> components: "you write with it" {style.opacity: 0}
components -> session: "declared in" {style.opacity: 0}
shell -> session: "builds and connects" {style.opacity: 0}
session -> app {style.opacity: 0}
steps: {
  1: {
    components: {
      class: step
      tooltip: The classes you write, or install from a plugin. Devices describe your hardware, presenters hold the application logic, and views show it on screen.
    }
    (sdk -> components)[0].style.opacity: 1
  }
  2: {
    session: {
      class: step
      tooltip: A session is one running application. You declare its components in a Python class or list them in a session file.
    }
    (components -> session)[0].style.opacity: 1
  }
  3: {
    shell: {
      class: layer
      tooltip: Discovers plugins, builds their components into a session, connects them, and launches the application.
    }
    app.class: current
    (shell -> session)[0].style.opacity: 1
    (session -> app)[0].style.opacity: 1
  }
}
```

A component is a [device, presenter or view](components.md), and a
[plugin](glossary.md#plugin) is an installed package that offers components;
a [session](glossary.md#session) is where you put them together.

## Design philosophy

Three ideas shape how `redsun` is built:

1. It builds on tools that already exist: `redsun` uses the hardware
   protocols of [`bluesky`](glossary.md#bluesky),
   [`ophyd-async`](glossary.md#ophyd-async) for devices and Qt for the window,
   rather than writing its own. What it adds is what you need to put them
   together into one application.
2. You take only what you need. Each component stands on its own, so a
   session holds only the ones you declare, and a plugin that offers a motor
   controller works without one that offers a camera.
3. Your data stays yours. `redsun` gives every file a place and a name,
   but your devices write the data, in the formats they choose, and what the
   data means and how you organize it is up to you.

## Why not use Bluesky directly?

`bluesky` runs acquisitions, but it leaves the application around them to
you: you drive the [`RunEngine`](glossary.md#runengine) from a command line or
`IPython`, and the rest is expected to exist already. Step through the
diagram to compare where that rest comes from at a large facility and on a
bench:

```d2 title="What surrounds a bluesky acquisition"
...@diagrams/style
direction: right
run: "bluesky RunEngine\nruns the acquisition" {
  class: layer
  width: 230
  height: 90
}
hardware: "hardware control" {class: step; width: 220; height: 70}
running: "keeping it running" {class: step; width: 220; height: 70}
screen: "what the user sees" {class: step; width: 220; height: 70}
data: "where the data goes" {class: hidden; width: 220; height: 70}
run -> hardware
run -> running
run -> screen
run -> data: {style.opacity: 0}
scenarios: {
  facility: {
    run.label: "bluesky RunEngine\nfrom a command line\nor IPython"
    hardware: "a control system\nsuch as EPICS or Tango" {class: current}
    running: "facility staff" {class: current}
    screen: "separate programs\nshow the instrument" {class: current}
  }
  bench: {
    run.label: "bluesky RunEngine\nin one application"
    hardware: "services that\nspeak EPICS" {class: current}
    running: "redsun starts and\nstops the services" {
      class: current
      tooltip: A service you declare with Launch runs while the session does. One you declare with Attach already runs elsewhere, and redsun only connects your devices to it.
    }
    screen: "the window\nredsun builds" {class: current}
    data: "redsun decides\nwhere data goes" {class: current}
    (run -> data)[0].style.opacity: 1
  }
}
```

At the facilities `bluesky` was developed at, a control system such as
[EPICS] or [Tango], its staff and the display programs already exist. A bench
setup, one instrument driven by one person through a window as with
[Micro-Manager], has none of that, so `redsun` supplies it, still speaking
EPICS through the [services](glossary.md#service) your devices talk to.

## Coming from Micro-Manager

If you've used Micro-Manager, many ideas in `redsun` will feel familiar,
although the pieces are divided differently. These are the closest matches:

| Micro-Manager | `redsun` |
| --- | --- |
| device adapter | a [device](glossary.md#device), preferably with a [service](glossary.md#service) to reach the hardware |
| hardware configuration file | [session file](glossary.md#session-file) |
| multi-dimensional acquisition | [plan](glossary.md#plan) |
| live mode | a plan that runs until it is stopped, see [Plans](plans.md#continuous-plans) |
| plugin | a [plugin](glossary.md#plugin) providing [components](glossary.md#component) |

## What redsun leaves to you

`redsun` gives you the framework, and everything specific to your instrument
comes from you or from a plugin:

| Not included | Where it comes from |
| --- | --- |
| hardware drivers | the devices and services you write or install |
| an image viewer | a [view](glossary.md#view) you write |
| a writer for acquisition files | the device or its service, see [Where a device writes](components.md#where-a-device-writes) |

For common tasks, `redsun` ships
[built-in components](plugins.md#built-in-components) you can use instead of
writing your own. When you do write a panel of your own for your plans,
`redsun` still builds the [plan widget](glossary.md#plan-widget) of each one;
see [Qt widgets](qt-widgets.md).

`redsun` also doesn't restart a service that crashes, and a program can run
only one [frontend](glossary.md#frontend). [Limitations](limits.md) explains
both.

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[micro-manager]: https://micro-manager.org/
[epics]: https://epics-controls.org/
[tango]: https://www.tango-controls.org/
