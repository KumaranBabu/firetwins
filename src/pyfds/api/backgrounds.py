"""Floor-plan backgrounds and tracing a plan into walls (IMP-04). Accessible via ``api.backgrounds``."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pyfds.domain.editor_state import Background

from .base import _UndoableStore

if TYPE_CHECKING:
    from .facade import FdsApi


class BackgroundManager(_UndoableStore):
    """Pictures (PNG, JPG, BMP, GIF, TGA, TIFF) and PDF pages placed under the model as drawing aids.

    ``add`` stores where the picture sits (lower-left corner, width in metres); ``trace`` turns the dark
    lines of a plan into ``&OBST`` boxes. Backgrounds are saved in the ``.pyfds`` file and never written
    to FDS. Every change is one undo step.
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    @property
    def _items(self) -> Dict[str, Background]:
        return self._api.project.editor.backgrounds

    def _capture_state(self):
        return {k: Background(**vars(v)) for k, v in self._items.items()}

    def _restore_state(self, state) -> None:
        self._items.clear()
        self._items.update(state)

    def all(self) -> List[Background]:
        return list(self._items.values())

    def get(self, name: str) -> Optional[Background]:
        return self._items.get(name)

    def _need(self, name: str) -> Background:
        b = self._items.get(name)
        if b is None:
            raise KeyError(f"background {name!r} not found")
        return b

    def add(self, path: str, name: Optional[str] = None, width: float = 10.0, x: float = 0.0, y: float = 0.0,
            z: float = 0.0, page: int = 0, opacity: float = 0.5, floor: str = "") -> Background:
        """Place a plan picture or PDF page. *width* is its real width in metres."""
        from pathlib import Path
        from pyfds.io.plan_reader import kind_of, read_gray
        if width <= 0:
            raise ValueError("width must be positive")
        if not 0.0 <= opacity <= 1.0:
            raise ValueError("opacity must be between 0 and 1")
        kind = kind_of(path)
        read_gray(path, page)                                   # fail now if unreadable
        name = name or Path(path).stem
        if name in self._items:
            raise ValueError(f"background {name!r} already exists")
        bg = Background(name=name, path=str(path), kind=kind, page=page, x=x, y=y, z=z, width=width,
                        opacity=opacity, floor=floor)
        return self._do(f"add background {name}", lambda: self._items.setdefault(name, bg))

    def update(self, name: str, **fields) -> Background:
        """Change position, size, opacity, visibility or floor."""
        self._need(name)
        known = set(vars(Background("a", "b")))
        bad = sorted(set(fields) - (known - {"name", "path", "kind"}))
        if bad:
            raise AttributeError(f"cannot change: {', '.join(bad)}")
        if "width" in fields and fields["width"] <= 0:
            raise ValueError("width must be positive")

        def act():
            b = self._items[name]
            for k, v in fields.items():
                setattr(b, k, v)
            return b
        return self._do(f"edit background {name}", act)

    def remove(self, name: str) -> None:
        self._need(name)
        self._do(f"remove background {name}", lambda: self._items.pop(name))

    def extent(self, name: str) -> List[float]:
        """``[x_min, x_max, y_min, y_max]`` the picture covers, in metres."""
        from pyfds.io.plan_reader import read_gray
        b = self._need(name)
        h, w = read_gray(b.path, b.page).shape
        return [b.x, b.x + b.width, b.y, b.y + b.width * h / w]

    def trace(self, name: str, height: float = 2.5, cell: float = 0.1, surf_id: str = "INERT",
              threshold: int = 128, min_fill: float = 0.3, max_boxes: int = 5000,
              prefix: str = "PLAN") -> List[Any]:
        """Make walls from the dark lines of a background: cells of *cell* metres that are at least
        *min_fill* dark become boxes *height* tall, starting at the background's z (one undo step)."""
        from pyfds.domain.plan_trace import trace
        from pyfds.io.plan_reader import read_gray
        if height <= 0:
            raise ValueError("height must be positive")
        b = self._need(name)
        rects = trace(read_gray(b.path, b.page), width_m=b.width, origin=(b.x, b.y), cell=cell,
                      threshold=threshold, min_fill=min_fill, max_boxes=max_boxes)
        if not rects:
            raise ValueError(f"no dark lines found in {name!r}; lower the threshold or min_fill")
        boxes = [(x0, x1, y0, y1, b.z, b.z + height) for x0, x1, y0, y1 in rects]
        return self._api.geom._add_boxes(boxes, prefix, surf_id, None, f"trace plan {name}")
