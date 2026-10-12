"""The Frame record the viewer produces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from pyfds.results.viz import colorbar as cb
from pyfds.results.viz import model as vm
from pyfds.results.viz.tree import NavNode


@dataclass
class Frame:
    """Everything to draw at one playback time."""
    time: float
    items: List[Tuple[NavNode, Any]] = field(default_factory=list)       # (node, primitive)
    overlay: str = ""
    camera: Optional[vm.Viewpoint] = None
    colorbars: List[Tuple[str, str, cb.ColorbarModel]] = field(default_factory=list)   # (quantity, units, bar)

    def of_kind(self, kind: str) -> List[Any]:
        return [p for n, p in self.items if n.kind == kind]
