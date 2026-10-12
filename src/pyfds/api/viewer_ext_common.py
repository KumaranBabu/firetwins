"""Renderer callable type."""
from __future__ import annotations

from typing import Callable, Tuple


#: ``renderer(path, size, time, view_name) -> None``: draws the current scene to an image file
Renderer = Callable[[str, Tuple[int, int], float, str], None]
