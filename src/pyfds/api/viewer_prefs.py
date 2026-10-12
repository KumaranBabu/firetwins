"""ViewerManager: FDS, smoke, vector and particle preferences."""
from __future__ import annotations

import copy
from typing import Any, Optional, Sequence

from pyfds.results.viz import model as vm


class ViewerManagerPrefsMixin:
    def set_fds_preferences(self, time_offset: Optional[float] = None, interpolate: Optional[bool] = None,
                            obscure_types: Optional[Sequence[str]] = None) -> vm.FdsPreferences:
        f = self.viz.fds
        if time_offset is not None:
            f.time_offset = float(time_offset)
        if interpolate is not None:
            f.interpolate = bool(interpolate)
        if obscure_types is not None:
            f.obscure_types = list(obscure_types)
        self._playback = None
        self.dirty = True
        return f

    # -- per-kind properties --------------------------------------------------------------------------------
    def set_smoke3d(self, preset: Optional[str] = None, **fields: Any) -> vm.Smoke3DProps:
        p = copy.deepcopy(self.viz.smoke3d)
        if preset is not None:
            vm.apply_smoke_preset(p, preset)
        for k, v in fields.items():
            if k not in vm.Smoke3DProps.__dataclass_fields__:
                raise AttributeError(f"unknown smoke property {k!r}")
            setattr(p, k, v)
        if fields and preset is None and p.preset != "custom":
            p.preset = "custom"
        bad = p.problems()
        if bad:
            raise ValueError("; ".join(bad))
        self.viz.smoke3d = p
        self.dirty = True
        return p

    def set_slice_vectors(self, node_id: str, factor: Optional[float] = None, step: Optional[int] = None) -> vm.SliceVectorProps:
        node = self.node(node_id)
        p = self.viz.slice_vectors.setdefault(node.quantity + "|" + node.label, vm.SliceVectorProps())
        if factor is not None:
            if factor <= 0:
                raise ValueError("vector factor must be positive")
            p.factor = float(factor)
        if step is not None:
            if step < 1:
                raise ValueError("vector step must be at least 1")
            p.step = int(step)
        self.dirty = True
        return p

    def set_particles(self, class_name: str, trail_time: Optional[float] = None, color: Optional[str] = None,
                      size: Optional[float] = None) -> vm.ParticleProps:
        p = self.viz.particles.setdefault(class_name, vm.ParticleProps())
        if trail_time is not None:
            if trail_time < 0:
                raise ValueError("trail time must not be negative")
            p.trail_time = float(trail_time)
        if color is not None:
            names = {q[0] for c in (self.run.particle_classes if self.run else []) if c.name == class_name for q in c.quantities}
            if color != "default" and self.run is not None and color not in names:
                raise KeyError(f"particle class {class_name!r} has no quantity {color!r}; has {sorted(names)}")
            p.color = color
        if size is not None:
            if size <= 0:
                raise ValueError("particle size must be positive")
            p.size = float(size)
        self.dirty = True
        return p

    def set_data3d_properties(self, group_id: str, sample_factor: float) -> None:
        if sample_factor <= 0:
            raise ValueError("sample factor must be positive")
        self.viz.data3d[group_id] = vm.Data3DProps(float(sample_factor))
        self.dirty = True
