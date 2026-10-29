"""SsfScriptBuilder: load commands."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .scripting_common import _SsfCommand, _unsupported, slcf_spec

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
        *,
        cell_centered: bool = False,
    ) -> "SsfScriptBuilder":
        """
        Load the slice of *quantity* on the plane ``axis`` (1=x, 2=y, 3=z) at coordinate *position* (metres), on
        every mesh that has it. (*mesh* and *index* are kept for old callers and not used by Smokeview's script.)

        A slice written with ``CELL_CENTERED=.TRUE.`` needs *cell_centered*: Smokeview's LOADSLICE does not load
        those ("Slice files of type ... failed to load"), so they go through LOADSLCF, which names the slice the
        way the &SLCF line does.

        Parameters
        ----------
        quantity : str
            FDS quantity string e.g. ``"TEMPERATURE"``.
        mesh : int
            1-based mesh index.
        index : int
            nth occurrence of this quantity for this mesh.
        """
        if cell_centered:
            self._commands.append(_SsfCommand("LOADSLCF", [slcf_spec(quantity, axis, position, cell_centered=True)],
                                              comment=f"cell-centred slice {quantity!r}"))
            return self
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

    def load_plot3d(self, time: float, mesh: int = 1) -> "SsfScriptBuilder":
        """Load the Plot3D file of *mesh* written nearest *time* seconds (Smokeview's LOADPLOT3D takes the mesh
        and the time; which quantity is shown is chosen in Smokeview)."""
        self._commands.append(_SsfCommand(
            "LOADPLOT3D", [f"{mesh} {time:g}"],
            comment=f"plot3d mesh {mesh} t = {time}",
        ))
        return self

    def load_vector(self, quantity: str = "VELOCITY", axis: int = 2, position: float = 0.0, *,
                    cell_centered: bool = False) -> "SsfScriptBuilder":
        """Load the vector slice written with ``VECTOR=.TRUE.`` for *quantity* on the plane ``axis`` at *position*:
        the slice coloured by *quantity* with velocity arrows (U, V, W-VELOCITY are loaded with it)."""
        self._commands.append(_SsfCommand(
            "LOADSLCF", [slcf_spec(quantity, axis, position, cell_centered=cell_centered, vector=True)],
            comment=f"vector slice {quantity!r}",
        ))
        return self

    def set_frame(self, frame: int) -> "SsfScriptBuilder":
        """Not available: Smokeview scripts move through a run by time only."""
        raise _unsupported("jump to an output frame number", "Use set_time() with the frame's time.")
