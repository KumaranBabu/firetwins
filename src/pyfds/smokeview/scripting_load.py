"""SsfScriptBuilder: load commands."""
from __future__ import annotations

from typing import TYPE_CHECKING

from typing import Optional

from .scripting_common import _SsfCommand

if TYPE_CHECKING:
    from .scripting import SsfScriptBuilder


class SsfScriptBuilderLoadMixin:
    def load_slice(
        self,
        quantity: str,
        mesh: int = 1,
        index: int = 1,
        axis: int = 2,
        position: float = 0.0,
    ) -> "SsfScriptBuilder":
        """
        Load the slice of *quantity* on the plane ``axis`` (1=x, 2=y, 3=z) at coordinate *position* (metres).
        (*mesh* and *index* are kept for old callers and not used by Smokeview's script.)

        Parameters
        ----------
        quantity : str
            FDS quantity string e.g. ``"TEMPERATURE"``.
        mesh : int
            1-based mesh index.
        index : int
            nth occurrence of this quantity for this mesh.
        """
        if axis not in (1, 2, 3):
            raise ValueError("axis must be 1 (x), 2 (y) or 3 (z)")
        self._commands.append(_SsfCommand(
            "LOADSLICE", [quantity, f"{axis} {position:g}"],
            comment=f"slice {quantity!r} mesh {mesh}",
        ))
        return self

    def load_boundary(self, quantity: Optional[str] = None, mesh: int = 1) -> "SsfScriptBuilder":
        """Activate a boundary quantity visualization."""
        # Smokeview's keywords take the quantity alone and load it on every mesh (checked against Smokeview 6.10.1:
        # the keywords used before - LOADSMOKE3D, LOADISOSURFACE, LOADPARTICLE - stopped the script as unknown).
        # *mesh* and *index* are kept for old callers.
        self._commands.append(_SsfCommand(
            "LOADBOUNDARY", [quantity] if quantity else [],
            comment=f"boundary {quantity!r}",
        ))
        return self

    def load_isosurface(self, quantity: str, mesh: int = 1) -> "SsfScriptBuilder":
        """Activate an isosurface visualization."""
        self._commands.append(_SsfCommand(
            "LOADISO", [quantity],
            comment=f"isosurface {quantity!r}",
        ))
        return self

    def load_smoke3d(self, quantity: str, mesh: int = 1) -> "SsfScriptBuilder":
        """Activate a 3-D smoke/fire visualization (``SOOT DENSITY``, ``HRRPUV`` ...)."""
        self._commands.append(_SsfCommand(
            "LOAD3DSMOKE", [quantity],
            comment=f"3D smoke {quantity!r}",
        ))
        return self

    def load_particle(self, mesh: int = 1, index: int = 1) -> "SsfScriptBuilder":
        """Activate the particle files (all meshes)."""
        self._commands.append(_SsfCommand(
            "LOADPARTICLES", [],
            comment="particles",
        ))
        return self

    def load_plot3d(self, quantity: str, mesh: int = 1,
                    index: int = 1) -> "SsfScriptBuilder":
        """Activate a Plot3D quantity visualization."""
        self._commands.append(_SsfCommand(
            "LOADPLOT3D", [str(mesh), str(index), quantity],
            comment=f"plot3d {quantity!r} mesh {mesh}",
        ))
        return self

    def load_vector(self, quantity: str = "VELOCITY",
                    mesh: int = 1) -> "SsfScriptBuilder":
        """Activate a vector-field visualization."""
        self._commands.append(_SsfCommand(
            "LOADVECTOR", [str(mesh), "1", quantity],
            comment=f"vector {quantity!r} mesh {mesh}",
        ))
        return self

    def set_frame(self, frame: int) -> "SsfScriptBuilder":
        """Jump to a specific output frame number (0-based)."""
        self._commands.append(_SsfCommand(
            "SETFRAME", [str(frame)],
            comment=f"frame {frame}",
        ))
        return self
