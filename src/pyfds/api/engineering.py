"""Engineering calculators and analyses.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING


if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class EngineeringManager:
    """
    Fire engineering calculators and design-tool helpers.

    Accessible via ``api.engineering``.

    Methods
    -------
    characterise_fire      — t-squared fire characterisation
    recommend_cell_size    — D*-based FDS cell size advice
    mesh_wizard            — auto-configure mesh from fire parameters
    ceiling_jet            — Alpert (1972) ceiling jet
    heskestad_plume        — Heskestad plume temperature / velocity
    critical_velocity      — Kennedy tunnel critical velocity
    smoke_filling_time     — NFPA 92 smoke filling time
    two_layer_zone_model   — CFAST-style two-zone quick-calc
    detector_response_time — RTI-based detector activation time
    fuel                   — look up a predefined FDS6 fuel reaction
    list_fuels             — list all fuel names in the library
    add_fuel_reaction      — add a library fuel as a Reaction to the project
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    # ── Fire characterisation ─────────────────────────────────────────────────

    def characterise_fire(self, hrr_kw: float, growth: str = "MEDIUM",
                          **kwargs) -> Any:
        """Return a :class:`FireGrowthResult` for *hrr_kw* and *growth* rate."""
        from pyfds.engineering import characterise_fire, GrowthRate
        gr = GrowthRate[growth.upper()] if isinstance(growth, str) else growth
        return characterise_fire(hrr_kw=hrr_kw, growth=gr, **kwargs)

    def recommend_cell_size(self, hrr_kw: float, **kwargs) -> Any:
        """Return a :class:`MeshAdvice` with recommended FDS cell sizes."""
        from pyfds.engineering import recommend_cell_size
        return recommend_cell_size(hrr_kw, **kwargs)

    def mesh_wizard(
        self,
        hrr_kw: float,
        room_xb: tuple,
        target_cells_millions: float = 2.0,
        growth: str = "MEDIUM",
        name: str = "AutoMesh",
    ) -> Any:
        """
        Auto-configure a single FDS mesh for a room fire.

        Picks the coarsest cell size that satisfies the D*/dx ≥ 5 criterion
        and targets *target_cells_millions* total cells.

        Returns the created :class:`Mesh` entity.
        """
        from pyfds.domain.model import Mesh
        from pyfds.engineering import recommend_cell_size
        from pyfds.automation.commands import AddEntityCommand

        advice = recommend_cell_size(hrr_kw)
        dx = advice.dx_recommended_m
        x0, x1, y0, y1, z0, z1 = room_xb
        nx = max(2, round((x1 - x0) / dx))
        ny = max(2, round((y1 - y0) / dx))
        nz = max(2, round((z1 - z0) / dx))

        # Scale down if over cell budget
        total = nx * ny * nz
        limit = int(target_cells_millions * 1e6)
        if total > limit:
            scale = (limit / total) ** (1 / 3)
            nx = max(2, round(nx * scale))
            ny = max(2, round(ny * scale))
            nz = max(2, round(nz * scale))

        mesh = Mesh(name=name,
                    x_min=x0, x_max=x1,
                    y_min=y0, y_max=y1,
                    z_min=z0, z_max=z1,
                    cell_count=(nx, ny, nz))
        self._api.history.execute(AddEntityCommand(self._api.project, mesh))
        return mesh

    # ── Plume / ceiling jet ───────────────────────────────────────────────────

    def ceiling_jet(self, hrr_kw: float, r: float, H: float) -> Any:
        """Return a :class:`CeilingJetResult` (Alpert 1972)."""
        from pyfds.engineering import alpert_ceiling_jet
        return alpert_ceiling_jet(hrr_kw=hrr_kw, r=r, H=H)

    def heskestad_plume(self, hrr_kw: float, z: float) -> Any:
        """Return a :class:`HeskestadResult` at height *z* above the fire."""
        from pyfds.engineering import heskestad_plume
        return heskestad_plume(hrr_kw=hrr_kw, z=z)

    # ── Tunnel ───────────────────────────────────────────────────────────────

    def critical_velocity(self, hrr_kw: float, tunnel_height_m: float,
                          tunnel_width_m: float, **kwargs) -> Any:
        """Return a :class:`CriticalVelocityResult` (Kennedy 1996)."""
        from pyfds.engineering import critical_velocity
        return critical_velocity(hrr_kw=hrr_kw,
                                 tunnel_height_m=tunnel_height_m,
                                 tunnel_width_m=tunnel_width_m,
                                 **kwargs)

    def smoke_filling_time(self, hrr_kw: float, floor_area_m2: float,
                           room_height_m: float, z_interface_m: float,
                           **kwargs) -> float:
        """Return NFPA 92 smoke filling time (s) to *z_interface_m*."""
        from pyfds.engineering import smoke_filling_time
        return smoke_filling_time(hrr_kw=hrr_kw,
                                  A_floor=floor_area_m2,
                                  H_room=room_height_m,
                                  z_interface=z_interface_m,
                                  **kwargs)

    # ── Zone model ────────────────────────────────────────────────────────────

    def two_layer_zone_model(self, hrr_kw: float, room_height_m: float,
                             floor_area_m2: float, **kwargs) -> Any:
        """Return a :class:`ZoneModelResult` from the two-layer zone model."""
        from pyfds.engineering import two_layer_zone_model
        return two_layer_zone_model(hrr_kw=hrr_kw,
                                    room_height_m=room_height_m,
                                    floor_area_m2=floor_area_m2,
                                    **kwargs)

    def detector_response_time(self, hrr_kw: float, ceiling_height_m: float,
                               detector_radial_distance_m: float,
                               **kwargs) -> Any:
        """Return a :class:`DetectorResponseResult` for a heat detector."""
        from pyfds.engineering import detector_response_time
        return detector_response_time(hrr_kw=hrr_kw,
                                      ceiling_height_m=ceiling_height_m,
                                      detector_radial_distance_m=detector_radial_distance_m,
                                      **kwargs)

    # ── Reaction library ─────────────────────────────────────────────────────

    def list_fuels(self):
        """Return sorted list of predefined fuel names."""
        from pyfds.domain.reactions import list_fuels
        return list_fuels()

    def fuel(self, fuel_name: str) -> dict:
        """Return raw parameter dict for *fuel_name* from the library."""
        from pyfds.domain.reactions import get_fuel
        return get_fuel(fuel_name)

    def add_fuel_reaction(self, fuel_name: str,
                          reaction_name: str = None) -> Any:
        """
        Create a ``Reaction`` from the built-in fuel library and add it to
        the active project.

        Returns the created ``Reaction`` entity.
        """
        from pyfds.domain.reactions import make_reaction
        from pyfds.automation.commands import AddEntityCommand
        r = make_reaction(fuel_name, reaction_name)
        self._api.history.execute(AddEntityCommand(self._api.project, r))
        return r

    def export_materials(self, filepath: str, fmt: str = "json") -> None:
        """Export MATERIAL_PRESETS to *filepath* in ``"json"`` or ``"csv"`` format."""
        from pyfds.domain.db_export import export_materials
        export_materials(filepath, fmt=fmt)

    def export_surfaces(self, filepath: str, fmt: str = "json") -> None:
        """Export SURFACE_PRESETS to *filepath* in ``"json"`` or ``"csv"`` format."""
        from pyfds.domain.db_export import export_surfaces
        export_surfaces(filepath, fmt=fmt)

    def export_fuels(self, filepath: str, fmt: str = "json") -> None:
        """Export FUEL_LIBRARY to *filepath* in ``"json"`` or ``"csv"`` format."""
        from pyfds.domain.db_export import export_fuels
        export_fuels(filepath, fmt=fmt)

    def export_db(
        self,
        dirpath: str,
        *,
        fmt: str = "json",
        stem: str = "pyfds_db",
    ) -> dict:
        """
        Export all three databases (materials, surfaces, fuels) to *dirpath*.

        Returns a ``{db_name: filepath}`` dict of the files written.
        """
        from pyfds.domain.db_export import export_all
        return export_all(dirpath, fmt=fmt, stem=stem)
