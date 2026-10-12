"""Cursor snapping: ``api.snapping`` (UX-04).

The settings live on the viewport (``api.viewport.set_snap(...)``); this applies them to a point using
the project's objects and meshes - see :mod:`pyfds.domain.snapping` for the rules. A view calls
``snap(point, anchor=...)`` on every mouse move and passes ``enabled=False`` while ALT is held and
``lock_direction=`` while Shift is held.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

from pyfds.domain import snapping as _s
from pyfds.domain.snapping import SnapResult

__all__ = ["SnapManager", "SnapResult"]


class SnapManager:
    def __init__(self, api) -> None:
        self._api = api

    @property
    def settings(self):
        return self._api.viewport.state.snap

    def kinds(self) -> list:
        """Snap kinds switched on by the current viewport settings, in priority order."""
        s = self.settings
        on = {"vertex": s.snap_to_vertex, "edge": s.snap_to_edge, "face": s.snap_to_face,
              "mesh_point": s.snap_to_mesh, "mesh_line": s.snap_to_mesh, "mesh_plane": s.snap_to_mesh,
              "grid": s.snap_to_grid}
        return [k for k in _s.PRIORITY if on[k]]

    def snap(self, point: Sequence[float], anchor: Optional[Sequence[float]] = None, *, enabled: Optional[bool] = None,
             lock_direction: Optional[Sequence[float]] = None, plane: Optional[Tuple[str, float]] = None,
             **overrides: Any) -> SnapResult:
        """Snap *point* with the viewport's settings. *overrides* may replace ``tolerance``, ``grid_size``,
        ``kinds``, ``ortho`` or ``polar_step_deg`` for this call only."""
        st = self.settings
        args = dict(tolerance=st.tolerance, grid_size=st.grid_size, kinds=self.kinds(), ortho=st.ortho,
                    polar_step_deg=st.polar_step_deg)
        bad = set(overrides) - set(args)
        if bad:
            raise TypeError(f"unknown snap options: {sorted(bad)}")
        args.update(overrides)
        return _s.snap(point, self._api.project, enabled=st.enabled if enabled is None else enabled,
                       anchor=anchor, lock_direction=lock_direction, plane=plane, **args)
