"""ViewerExtras: dimensions, labels and floors."""
from __future__ import annotations

import copy
from typing import List, Optional, Sequence

from pyfds.results.viz import annotations as an
from pyfds.results.viz import floors as fl
from pyfds.results.viz import model as vm


class ViewerExtrasAnnotationsMixin:
    # -- annotations -----------------------------------------------------------------------------------------------
    def add_dimension(self, p1: Sequence[float], p2: Sequence[float], mode: str = "feature", offset: float = 0.0) -> vm.Dimension:
        d = an.add_dimension(self.viz, p1, p2, mode, offset)
        self._rebuild()
        self.dirty = True
        return d

    def add_label(self, text: str, anchor: Sequence[float], position: Optional[Sequence[float]] = None) -> vm.Label:
        lab = an.add_label(self.viz, text, anchor, position)
        self._rebuild()
        self.dirty = True
        return lab

    def remove_annotation(self, kind: str, index: int) -> None:
        an.remove_annotation(self.viz, kind, index)
        self._rebuild()
        self.dirty = True

    def rename_label(self, index: int, text: str) -> None:
        an.rename_label(self.viz, index, text)
        self._rebuild()
        self.dirty = True

    def dimension_geometry(self, index: int) -> an.DimensionGeometry:
        return an.dimension_geometry(self.viz.dimensions[index], self.viz.general.dimension_precision)

    def show_annotations(self, dimensions: Optional[bool] = None, labels: Optional[bool] = None) -> None:
        if dimensions is not None:
            self.viz.show_dimensions = bool(dimensions)
        if labels is not None:
            self.viz.show_labels = bool(labels)
        self.dirty = True

    # -- floors --------------------------------------------------------------------------------------------------------
    def set_floors(self, levels: Sequence[float]) -> vm.FloorSettings:
        fl.set_floors(self.viz.floors, levels)
        self.dirty = True
        return self.viz.floors

    def set_floor_layout(self, layout: Optional[str] = None, separation: Optional[float] = None,
                         clip_walls: Optional[bool] = None, wall_height: Optional[float] = None) -> vm.FloorSettings:
        trial = copy.deepcopy(self.viz.floors)
        if layout is not None:
            trial.layout = layout
        if separation is not None:
            trial.separation = float(separation)
        if clip_walls is not None:
            trial.clip_walls = bool(clip_walls)
        if wall_height is not None:
            trial.wall_height = float(wall_height)
        bad = fl.validate(trial)
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.floors = trial
        self.dirty = True
        return trial

    def show_floors(self, floors: Optional[Sequence[int]]) -> None:
        fl.set_visible(self.viz.floors, floors)
        self.dirty = True

    def show_floors_for_selection(self, z_min: float, z_max: float) -> List[int]:
        idx = fl.floors_for_selection(self.viz.floors, z_min, z_max)
        fl.set_visible(self.viz.floors, idx)
        self.dirty = True
        return idx
