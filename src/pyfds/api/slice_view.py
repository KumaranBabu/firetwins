"""Slice display settings and rendering: ``api.slice_view`` (RES-04).

The settings object (:class:`~pyfds.results.slice_display.SliceDisplay`) is what a colour-bar editor
edits; ``render`` / ``render_frames`` turn a slice result (or an ``.sf`` path) into images.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, List, Optional

from pyfds.results import slice_display as sd
from pyfds.results.slice_display import SliceDisplay


class SliceViewManager:
    def __init__(self, api) -> None:
        self._api = api

    def colormaps(self) -> List[str]:
        return list(sd.COLORMAPS)

    def defaults(self, quantity: str = "") -> SliceDisplay:
        return sd.default_display(quantity)

    def display(self, quantity: str = "", **options) -> SliceDisplay:
        """Defaults for *quantity* with *options* applied (validated)."""
        base = sd.default_display(quantity)
        bad = set(options) - set(asdict(base))
        if bad:
            raise TypeError(f"unknown display options: {sorted(bad)}")
        return replace(base, **options).checked()

    @staticmethod
    def _load(result: Any):
        if isinstance(result, str):
            from pyfds.results.reader import SliceReader
            return SliceReader.read(result)
        return result

    def _mesh(self, mesh: Any):
        return self._api.meshes.get(mesh) if isinstance(mesh, str) else mesh

    def bounds(self, result: Any, frame: int = -1, **options) -> tuple:
        r = self._load(result)
        return sd.bounds(r, self.display(r.quantity, **options), frame)

    def render(self, result: Any, filepath: str, frame: int = -1, mesh: Any = None, dpi: int = 100, **options) -> str:
        """Render one frame to *filepath* (PNG). *mesh* (name or Mesh) puts real coordinates on the axes."""
        r = self._load(result)
        return sd.render(r, filepath, frame, self.display(r.quantity, **options), self._mesh(mesh), dpi)

    def render_bytes(self, result: Any, frame: int = -1, mesh: Any = None, dpi: int = 100,
                     size: tuple = (7.0, 5.5), **options) -> bytes:
        """One frame as PNG bytes (what a viewer window shows)."""
        r = self._load(result)
        return sd.render(r, None, frame, self.display(r.quantity, **options), self._mesh(mesh), dpi, size)

    def render_frames(self, result: Any, outdir: str, prefix: str = "slice", frames: Optional[List[int]] = None,
                      mesh: Any = None, dpi: int = 100, **options) -> List[str]:
        r = self._load(result)
        return sd.render_frames(r, outdir, prefix, frames, self.display(r.quantity, **options), self._mesh(mesh), dpi)
