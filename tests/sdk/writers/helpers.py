"""Values the writer tests share."""

from __future__ import annotations

import numpy as np

from redsun.writers._base import ArrayShape

FRAME = ArrayShape.of((4, 4), np.uint16)
"""The shape and type of every frame a test store holds."""
