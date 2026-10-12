"""Multipliers (&MULT), rigid motions (&MOVE) and mesh stretching (&TRNX/Y/Z)."""
from __future__ import annotations

from typing import Any, Optional, Sequence

from .base import _CollectionManager
from .species import _unique


class MultManager(_CollectionManager):
    """Array multipliers: ``api.mults``."""

    def __init__(self, api) -> None:
        from pyfds.domain.model import Mult
        super().__init__(api, Mult)

    def add_mult(self, name: Optional[str] = None, *, dx: float = 0.0, dy: float = 0.0,
                 dz: float = 0.0, i: Sequence[int] = (0, 0), j: Sequence[int] = (0, 0),
                 k: Sequence[int] = (0, 0), **fields) -> Any:
        """Array of copies: spacing ``dx/dy/dz``; index ranges ``i/j/k`` = (lower, upper)."""
        from pyfds.domain.model import Mult
        for label, rng in (("i", i), ("j", j), ("k", k)):
            if len(rng) != 2 or rng[0] > rng[1]:
                raise ValueError(f"{label} must be (lower, upper) with lower <= upper")
        if name and self.get(name) is not None:
            raise ValueError(f"mult {name!r} already exists")
        mult = Mult(name=name or _unique(self, "MULT"), dx=dx, dy=dy, dz=dz,
                    i_lower=i[0], i_upper=i[1], j_lower=j[0], j_upper=j[1],
                    k_lower=k[0], k_upper=k[1], **fields)
        self.add(mult)
        return mult

    @staticmethod
    def copies(mult) -> int:
        """Number of copies the multiplier generates."""
        return ((mult.i_upper - mult.i_lower + 1) * (mult.j_upper - mult.j_lower + 1)
                * (mult.k_upper - mult.k_lower + 1))


class MoveManager(_CollectionManager):
    """Rigid transforms applied to GEOM/OBST: ``api.moves``."""

    def __init__(self, api) -> None:
        from pyfds.domain.model import Move
        super().__init__(api, Move)

    def add_move(self, name: Optional[str] = None, **fields) -> Any:
        from pyfds.domain.model import Move
        if name and self.get(name) is not None:
            raise ValueError(f"move {name!r} already exists")
        move = Move(name=name or _unique(self, "MOVE"), **fields)
        self.add(move)
        return move

    def add_translation(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
                        name: Optional[str] = None) -> Any:
        return self.add_move(name, dx=dx, dy=dy, dz=dz)

    def add_rotation(self, angle: float, axis: Sequence[float] = (0, 0, 1),
                     origin: Sequence[float] = (0, 0, 0), name: Optional[str] = None) -> Any:
        if len(axis) != 3 or len(origin) != 3:
            raise ValueError("axis and origin must be [x, y, z]")
        return self.add_move(name, rotation_angle=angle, axis=tuple(float(a) for a in axis),
                             x0=origin[0], y0=origin[1], z0=origin[2])


class MeshTransformManager(_CollectionManager):
    """Non-uniform mesh stretching control points: ``api.mesh_transforms``."""

    def __init__(self, api) -> None:
        from pyfds.domain.model import MeshTransform
        super().__init__(api, MeshTransform)

    def add_transform(self, direction: str, cc: float, pc: float = 0.5, mesh_number: int = 1,
                      ideriv: int = 0, name: Optional[str] = None) -> Any:
        from pyfds.domain.model import MeshTransform
        direction = direction.upper()
        if direction not in ("X", "Y", "Z"):
            raise ValueError("direction must be X, Y or Z")
        if not 0.0 <= pc <= 1.0:
            raise ValueError("pc must be within 0..1")
        trn = MeshTransform(name=name or _unique(self, f"TRN{direction}"), direction=direction,
                            cc=cc, pc=pc, mesh_number=mesh_number, ideriv=ideriv)
        self.add(trn)
        return trn
