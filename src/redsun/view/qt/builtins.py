"""Views shipped with ``redsun``.

Declare them with ``declare_view``, or name them in a YAML configuration
through the ``redsun`` plugin manifest (``plugin_name: redsun``).
"""

from ._log_view import LogView

__all__ = ["LogView"]
