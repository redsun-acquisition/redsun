# Presenters

`Presenters` represent the execution logic of your system.

Where `Devices` are "workers" (as they instruct your device to perform a certain task), `Presenters` **can be** "orchestrators", in the sense that they define the sequence of actions that workers must perform through Bluesky [plans].

We highlight "**can be**" because `Presenters` are not limited to that:

- they can consume Bluesky [documents] for on-the-fly processing, intermediate storage or redirection to a GUI (i.e. computing the FFT of an image and sending it to the GUI for display);
- they can provide manual control for device task execution and/or configuration;
  - in comparison to plans (which represents an experimental procedure), one may wish to - for example - manually move a motor stage from the GUI, or change the exposure time of a camera; the `Presenter` in this case acts as a middle-man between the GUI and the device, directly calling Bluesky methods and bypassing the `RunEngine`;
- they can act as communication points with external applications to trigger actions via a custom communication protocol (or wait for possible commands incoming by said applications).

`Presenters` are meant to communicate between each other via the [`VirtualBus`][redsun.virtual.VirtualBus], which takes care of redirecting information (commands and/or documents) to the appropriate destination (whether it is another `Presenter` or a `View`).

All presenters must implement the [`PPresenter`][redsun.presenter.PPresenter] interface to be recognized by Redsun.

The [`PPresenter`][redsun.presenter.PPresenter] requires two things in its initialization:

- a `name` which to be used as a unique identifier for the `Presenter` object
- a `Mapping[str, Device]` of the allocated devices in the session;

Additional parameters can be passed via keyword arguments, which are parsed from the session configuration file.

[plans]: https://blueskyproject.io/bluesky/main/plans.html
[documents]: https://blueskyproject.io/bluesky/main/documents.html
