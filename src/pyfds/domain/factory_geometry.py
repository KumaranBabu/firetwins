"""EntityFactory: meshes, obstructions, burners, vents, holes, moves."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class EntityFactoryGeometryMixin:
    def create_mesh(
        self,
        name: str,
        ijk: Tuple[int, int, int],
        xb: Tuple[float, ...],
        *,
        mpi_rank: Optional[int] = None,
        color: Optional[str] = None,
        cylindrical: bool = False,
    ) -> Any:
        from pyfds.domain.model import Mesh
        kw: Dict[str, Any] = dict(name=name, cell_count=tuple(int(v) for v in ijk))
        kw.update(self._xb_dict(xb))
        if mpi_rank is not None:
            kw["mpi_processor"] = mpi_rank
        if color:
            kw["color"] = color
        if cylindrical:
            kw["cylindrical"] = True
        return Mesh(**kw)

    def create_obstruction(
        self,
        name: str,
        xb: Tuple[float, ...],
        surf_id: str = "INERT",
        *,
        color: str = "GRAY",
        ctrl_id: Optional[str] = None,
        mult_id: Optional[str] = None,
        transparency: float = 0.0,
    ) -> Any:
        from pyfds.domain.model import Obstruction
        kw = dict(name=name, surface_id=surf_id, color=color,
                  transparency=transparency)
        kw.update(self._xb_dict(xb))
        if ctrl_id:
            kw["ctrl_id"] = ctrl_id
        if mult_id:
            kw["mult_id"] = mult_id
        return Obstruction(**kw)

    def create_burner(
        self,
        name: str,
        xb: Tuple[float, ...],
        hrrpua: float,
        *,
        tau_q: float = 1.0,
        ramp_q: Optional[str] = None,
        color: str = "RED",
    ) -> Any:
        """Create a burning surface (SURF with HRRPUA set)."""
        from pyfds.domain.model import Surface
        kw: Dict[str, Any] = dict(
            name=name,
            heat_release_rate=hrrpua,
            tau_q=tau_q,
            color=color,
        )
        if ramp_q:
            kw["ramp_q"] = ramp_q
        return Surface(**kw)

    def create_vent(
        self,
        name: str,
        xb: Tuple[float, ...],
        surf_id: str = "OPEN",
        *,
        ctrl_id: Optional[str] = None,
        dynamic_pressure: Optional[float] = None,
    ) -> Any:
        from pyfds.domain.model import Vent
        kw = dict(name=name, surface_id=surf_id)
        kw.update(self._xb_dict(xb))
        if ctrl_id:
            kw["ctrl_id"] = ctrl_id
        if dynamic_pressure is not None:
            kw["dynamic_pressure"] = dynamic_pressure
        return Vent(**kw)

    def create_hole(
        self,
        name: str,
        xb: Tuple[float, ...],
        *,
        ctrl_id: Optional[str] = None,
    ) -> Any:
        from pyfds.domain.model import Hole
        kw = dict(name=name)
        kw.update(self._xb_dict(xb))
        if ctrl_id:
            kw["ctrl_id"] = ctrl_id
        return Hole(**kw)

    def create_move(
        self,
        name: str,
        *,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        rotation_angle: Optional[float] = None,
        axis: Optional[Tuple[float, float, float]] = None,
        scale: float = 1.0,
    ) -> Any:
        """Create a MOVE namelist entity for geometry transformation."""
        from pyfds.domain.model import Move
        kw: Dict[str, Any] = dict(name=name, x=x, y=y, z=z, scale=scale)
        if rotation_angle is not None:
            kw["rotation_angle"] = rotation_angle
        if axis is not None:
            kw["axis"] = list(axis)
        return Move(**kw)
