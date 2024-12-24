# RedSun

```{warning}
This project is currently under active development and it may (and most likely will) receive breaking changes. Use at your own risk.
```

RedSun is an acquisition software written in [CPython], with the concept of building modular user interfaces for scientific data acquisition.

It leverages the [Bluesky] ecosystem to provide a flexible, hardware-agnostic and unopinionated framework for building a control software tailored to the specific needs of different users in different scientific fields.

The philosophy of RedSun is to:

- not "reinvent the wheel", but rather "ship the tools to build the wheel";
- be extensible and modular: pick only the tools you need to get the job done;
- give the control of your data (and metadata) to you: you decide what is what.

## Contents

```{toctree}
:maxdepth: 1

getting_started/index
api/index
```

## Indices and tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`

[bluesky]: https://blueskyproject.io/bluesky/main/index.html
[cpython]: https://www.python.org/
