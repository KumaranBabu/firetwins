"""ViewerExtras: section boxes and planes."""
from __future__ import annotations

import copy
from typing import Dict, Optional, Sequence, Tuple

from pyfds.results.viz import model as vm
from pyfds.results.viz import views as vw


class ViewerExtrasSectionsMixin:
    def add_section_box(self, selection_bounds: Optional[Sequence[float]] = None) -> vm.SectionBox:
        """View ▸ Add section box: around everything visible, or around the selected objects."""
        if self.viz.active_view is None:
            self.new_view()
        bounds = selection_bounds or (self.run.bounds() if self.run else (0, 1, 0, 1, 0, 1))
        box = vw.new_section_box(bounds, enabled_planes=())
        vw.set_section_box(self.viz, None, box)
        self.dirty = True
        return box

    def set_section_plane(self, plane: str, value: float, enabled: bool = True) -> vm.SectionBox:
        box = vw.active_section(self.viz)
        if box is None:
            raise ValueError("the active view has no section box; add one first")
        trial = copy.deepcopy(box)
        vw.set_plane(trial, plane, value, enabled)
        vw.set_section_box(self.viz, None, trial)
        self.dirty = True
        return trial

    def set_section_planes(self, planes: Dict[str, Tuple[bool, float]]) -> vm.SectionBox:
        """Set several planes at once (the Section Box dialog); nothing changes when the result is not a valid box."""
        box = vw.active_section(self.viz)
        if box is None:
            raise ValueError("the active view has no section box; add one first")
        trial = copy.deepcopy(box)
        for name, (on, value) in planes.items():
            trial.planes[name] = (bool(on), float(value))
        for axis in "xyz":
            a, b = trial.planes.get(axis + "_min"), trial.planes.get(axis + "_max")
            if a and b and a[0] and b[0] and a[1] >= b[1]:
                raise ValueError(f"{axis}_min must be smaller than {axis}_max")
        vw.set_section_box(self.viz, None, trial)
        self.dirty = True
        return trial

    def remove_section_box(self) -> None:
        vw.set_section_box(self.viz, None, None)
        self.dirty = True

    def enable_section_boxes(self, enabled: bool) -> None:
        box = vw.active_section(self.viz)
        if box is not None:
            box.enabled = bool(enabled)
            self.dirty = True
