"""
PyFDS Preset / Template Engine
================================
Pre-built fire scenario templates that produce a partially-configured
``FdsProject`` ready for geometry and device placement.

Usage::

    from pyfds.domain.presets import PresetEngine, list_presets

    eng = PresetEngine()
    print(list_presets())

    project = eng.apply("room_fire", hrr_kw=500, t_end=120.0)
    # project is a populated FdsProject; caller adds geometry, saves, runs.

Adding custom templates::

    @eng.register("my_scenario")
    def my_scenario(project, **kwargs):
        ...
        return project
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .model import (
    FdsProject, Mesh, Surface, Vent, Reaction, Material, Layer,
    Device, Slice, BoundaryFile, IsoSurface, SimulationParams,
    MiscParams, DumpParams,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template descriptor
# ---------------------------------------------------------------------------

@dataclass
class ScenarioTemplate:
    name: str
    description: str
    tags: List[str]
    defaults: Dict[str, Any]
    builder: Callable[..., FdsProject]

    def apply(self, **kwargs) -> FdsProject:
        merged = {**self.defaults, **kwargs}
        return self.builder(**merged)


# ---------------------------------------------------------------------------
# Preset Engine
# ---------------------------------------------------------------------------

class PresetEngine:
    """Registry and executor of scenario templates."""

    def __init__(self) -> None:
        self._registry: Dict[str, ScenarioTemplate] = {}
        self._register_builtins()

    # ── Registration ─────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> Callable:
        """Decorator to register a builder function as a named template."""
        def decorator(fn: Callable) -> Callable:
            self._registry[name] = ScenarioTemplate(
                name=name,
                description=description or fn.__doc__ or "",
                tags=tags or [],
                defaults=defaults or {},
                builder=fn,
            )
            return fn
        return decorator

    def add(self, template: ScenarioTemplate) -> None:
        self._registry[template.name] = template

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[ScenarioTemplate]:
        return self._registry.get(name)

    def apply(self, name: str, **kwargs) -> FdsProject:
        """
        Build and return a project from the named template.

        Parameters
        ----------
        name:
            Template identifier (see ``list_presets()``).
        **kwargs:
            Override template default parameters.

        Raises
        ------
        KeyError:
            If *name* is not a registered template.
        """
        tmpl = self._registry.get(name)
        if tmpl is None:
            raise KeyError(
                f"No preset named {name!r}. "
                f"Available: {sorted(self._registry)}"
            )
        project = tmpl.apply(**kwargs)
        logger.info("Preset %r applied → project chid=%r", name, project.chid)
        return project

    def names(self) -> List[str]:
        return sorted(self._registry.keys())

    def all_templates(self) -> List[ScenarioTemplate]:
        return list(self._registry.values())

    # ── Built-in presets ──────────────────────────────────────────────────────

    def _register_builtins(self) -> None:
        # ── Room fire ──────────────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="room_fire",
            description="Single compartment room fire with a single burner and thermocouples.",
            tags=["compartment", "residential", "beginner"],
            defaults={
                "chid":       "room_fire",
                "t_end":      60.0,
                "hrr_kw":     250.0,
                "room_x":     5.0,
                "room_y":     4.0,
                "room_z":     3.0,
                "cell_size":  0.1,
            },
            builder=_build_room_fire,
        ))

        # ── Corridor smoke ─────────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="corridor_smoke",
            description="Smoke spread in a long corridor with a doorway fire source.",
            tags=["egress", "smoke", "corridor"],
            defaults={
                "chid":      "corridor_smoke",
                "t_end":     120.0,
                "hrr_kw":    100.0,
                "length":    20.0,
                "width":     2.0,
                "height":    2.5,
                "cell_size": 0.1,
            },
            builder=_build_corridor_smoke,
        ))

        # ── Pool fire ──────────────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="pool_fire",
            description="Circular pool fire (heptane) in open domain for heat flux studies.",
            tags=["pool", "heptane", "validation"],
            defaults={
                "chid":        "pool_fire",
                "t_end":       60.0,
                "pool_dia":    0.3,
                "hrr_kw":      50.0,
                "domain_size": 3.0,
                "cell_size":   0.05,
            },
            builder=_build_pool_fire,
        ))

        # ── Atrium smoke filling ───────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="atrium_smoke",
            description="Smoke filling in a tall atrium with mechanical exhaust.",
            tags=["atrium", "smoke", "hvac"],
            defaults={
                "chid":       "atrium_smoke",
                "t_end":      180.0,
                "hrr_kw":     1000.0,
                "width":      20.0,
                "depth":      20.0,
                "height":     15.0,
                "cell_size":  0.25,
            },
            builder=_build_atrium_smoke,
        ))

        # ── Wildland interface ─────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="wildland_fire",
            description="Wind-driven grass fire approaching a structure.",
            tags=["wui", "outdoor", "wind"],
            defaults={
                "chid":       "wildland_fire",
                "t_end":      60.0,
                "wind_speed": 5.0,
                "domain_x":   50.0,
                "domain_y":   20.0,
                "domain_z":   10.0,
                "cell_size":  0.2,
            },
            builder=_build_wildland_fire,
        ))

        # ── Blank project ─────────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="blank",
            description="Empty FdsProject with sensible global defaults only.",
            tags=["generic"],
            defaults={"chid": "new_case", "t_end": 60.0},
            builder=_build_blank,
        ))


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------

def _build_blank(*, chid: str = "new_case", t_end: float = 60.0, **_) -> FdsProject:
    p = FdsProject()
    p.chid = chid
    p.params.t_end = t_end
    return p


def _build_room_fire(
    *,
    chid: str = "room_fire",
    t_end: float = 60.0,
    hrr_kw: float = 250.0,
    room_x: float = 5.0,
    room_y: float = 4.0,
    room_z: float = 3.0,
    cell_size: float = 0.1,
    **_,
) -> FdsProject:
    from .geometry import GeometryHelper
    p = FdsProject()
    p.chid = chid
    p.title = f"Room fire — HRR={hrr_kw} kW"
    p.params.t_end = t_end
    p.dump.dt_slcf = 1.0
    p.dump.dt_devc = 1.0

    # Mesh
    nx, ny, nz = GeometryHelper.auto_cell_count_from_box(
        room_x, room_y, room_z, cell_size)
    m = Mesh(name="Room", x_min=0, x_max=room_x, y_min=0, y_max=room_y,
             z_min=0, z_max=room_z, cell_count=(nx, ny, nz))
    p.add_entity(m)

    # Reaction
    reac = Reaction(name="HEPTANE", fuel="HEPTANE",
                    heat_of_combustion=44600.0, soot_yield=0.037)
    p.add_entity(reac)

    # Surfaces
    p.add_entity(Surface(name="Burner", heat_release_rate=hrr_kw / (0.5 * 0.5),
                          tau_q=10.0, color="RED"))
    p.add_entity(Surface(name="Concrete", color="GRAY"))

    # Open vents on all exterior faces
    for face in [
        Vent(name="X0", x_min=0, x_max=0, y_min=0, y_max=room_y, z_min=0, z_max=room_z, surface_id="OPEN"),
        Vent(name="X1", x_min=room_x, x_max=room_x, y_min=0, y_max=room_y, z_min=0, z_max=room_z, surface_id="OPEN"),
    ]:
        p.add_entity(face)

    # Thermocouple array
    for z in [0.3, 0.9, 1.5, 2.1, 2.7]:
        p.add_entity(Device(name=f"TC_z{z}", quantity="TEMPERATURE",
                             x=room_x / 2, y=room_y / 2, z=z))

    # Slice files
    p.add_entity(Slice(name="SLCF_X_MID", quantity="TEMPERATURE",
                        plane="X", position=room_x / 2))
    p.add_entity(Slice(name="SLCF_Z_SMOKE", quantity="VISIBILITY",
                        plane="Z", position=room_z / 2))
    p.add_entity(BoundaryFile(name="BNDF_WALL_T", quantity="WALL TEMPERATURE"))

    return p


# Attach auto_cell_count_from_box as a convenience to GeometryHelper
from .geometry import GeometryHelper as _GH
import math as _math

def _auto_cells(lx, ly, lz, dx):
    from .geometry import GeometryHelper
    nx = max(1, _math.ceil(lx / dx))
    ny = max(1, _math.ceil(ly / dx))
    nz = max(1, _math.ceil(lz / dx))
    return (GeometryHelper.nearest_poisson(nx),
            GeometryHelper.nearest_poisson(ny),
            GeometryHelper.nearest_poisson(nz))

_GH.auto_cell_count_from_box = staticmethod(_auto_cells)


def _build_corridor_smoke(
    *,
    chid: str = "corridor_smoke",
    t_end: float = 120.0,
    hrr_kw: float = 100.0,
    length: float = 20.0,
    width: float = 2.0,
    height: float = 2.5,
    cell_size: float = 0.1,
    **_,
) -> FdsProject:
    p = FdsProject()
    p.chid = chid
    p.title = f"Corridor smoke — L={length} m, HRR={hrr_kw} kW"
    p.params.t_end = t_end

    nx, ny, nz = _auto_cells(length, width, height, cell_size)
    p.add_entity(Mesh(name="Corridor", x_min=0, x_max=length,
                      y_min=0, y_max=width, z_min=0, z_max=height,
                      cell_count=(nx, ny, nz)))
    p.add_entity(Reaction(name="PROPANE", fuel="PROPANE",
                          heat_of_combustion=46300.0, soot_yield=0.024))
    p.add_entity(Surface(name="FireSource",
                          heat_release_rate=hrr_kw / (0.25 * 0.25), tau_q=10.0))
    p.add_entity(Vent(name="End1", x_min=0, x_max=0, y_min=0, y_max=width,
                      z_min=0, z_max=height, surface_id="OPEN"))
    p.add_entity(Vent(name="End2", x_min=length, x_max=length, y_min=0, y_max=width,
                      z_min=0, z_max=height, surface_id="OPEN"))
    # Smoke detector line
    for x in range(2, int(length), 2):
        p.add_entity(Device(name=f"SD_{x}m", quantity="VISIBILITY",
                             x=float(x), y=width / 2, z=height - 0.1))
    p.add_entity(Slice(name="SLCF_Y_MID", quantity="VISIBILITY",
                        plane="Y", position=width / 2))
    return p


def _build_pool_fire(
    *,
    chid: str = "pool_fire",
    t_end: float = 60.0,
    pool_dia: float = 0.3,
    hrr_kw: float = 50.0,
    domain_size: float = 3.0,
    cell_size: float = 0.05,
    **_,
) -> FdsProject:
    p = FdsProject()
    p.chid = chid
    p.title = f"Pool fire — D={pool_dia} m, HRR={hrr_kw} kW"
    p.params.t_end = t_end

    nx, ny, nz = _auto_cells(domain_size, domain_size, domain_size, cell_size)
    p.add_entity(Mesh(name="Domain", x_min=0, x_max=domain_size,
                      y_min=0, y_max=domain_size, z_min=0, z_max=domain_size,
                      cell_count=(nx, ny, nz)))
    p.add_entity(Reaction(name="HEPTANE", fuel="HEPTANE",
                          heat_of_combustion=44600.0, soot_yield=0.037,
                          co_yield=0.006))
    pool_area = 3.14159 * (pool_dia / 2) ** 2
    hrrpua = hrr_kw / pool_area
    p.add_entity(Surface(name="Pool", heat_release_rate=hrrpua, tau_q=1.0))
    mid = domain_size / 2
    r = pool_dia / 2
    p.add_entity(Vent(name="PoolSurface", x_min=mid - r, x_max=mid + r,
                      y_min=mid - r, y_max=mid + r, z_min=0.0, z_max=0.0,
                      surface_id="Pool"))
    # Open all sides
    for face in [
        Vent(name="Top", x_min=0, x_max=domain_size, y_min=0, y_max=domain_size,
             z_min=domain_size, z_max=domain_size, surface_id="OPEN"),
        Vent(name="XNeg", x_min=0, x_max=0, y_min=0, y_max=domain_size,
             z_min=0, z_max=domain_size, surface_id="OPEN"),
        Vent(name="XPos", x_min=domain_size, x_max=domain_size, y_min=0,
             y_max=domain_size, z_min=0, z_max=domain_size, surface_id="OPEN"),
        Vent(name="YNeg", x_min=0, x_max=domain_size, y_min=0, y_max=0,
             z_min=0, z_max=domain_size, surface_id="OPEN"),
        Vent(name="YPos", x_min=0, x_max=domain_size, y_min=domain_size,
             y_max=domain_size, z_min=0, z_max=domain_size, surface_id="OPEN"),
    ]:
        p.add_entity(face)
    # Radial heat flux probes
    for r_dist in [0.3, 0.6, 1.0, 1.5]:
        p.add_entity(Device(name=f"HF_{r_dist}m", quantity="RADIATIVE HEAT FLUX",
                             x=mid + r_dist, y=mid, z=0.5,
                             orientation=(-1.0, 0.0, 0.0)))
    p.add_entity(Slice(name="SLCF_Y_MID", quantity="TEMPERATURE",
                        plane="Y", position=mid))
    p.add_entity(IsoSurface(name="Flame_300C", quantity="TEMPERATURE", value=300.0))
    return p


def _build_atrium_smoke(
    *,
    chid: str = "atrium_smoke",
    t_end: float = 180.0,
    hrr_kw: float = 1000.0,
    width: float = 20.0,
    depth: float = 20.0,
    height: float = 15.0,
    cell_size: float = 0.25,
    **_,
) -> FdsProject:
    p = FdsProject()
    p.chid = chid
    p.title = f"Atrium smoke filling — HRR={hrr_kw} kW, H={height} m"
    p.params.t_end = t_end

    nx, ny, nz = _auto_cells(width, depth, height, cell_size)
    p.add_entity(Mesh(name="Atrium", x_min=0, x_max=width,
                      y_min=0, y_max=depth, z_min=0, z_max=height,
                      cell_count=(nx, ny, nz)))
    p.add_entity(Reaction(name="HEPTANE", fuel="HEPTANE",
                          heat_of_combustion=44600.0, soot_yield=0.037))
    p.add_entity(Surface(name="FireSource",
                          heat_release_rate=hrr_kw / (1.0 * 1.0), tau_q=30.0))
    cx, cy = width / 2, depth / 2
    p.add_entity(Vent(name="Burner", x_min=cx - 0.5, x_max=cx + 0.5,
                      y_min=cy - 0.5, y_max=cy + 0.5, z_min=0, z_max=0,
                      surface_id="FireSource"))
    # Smoke exhaust at roof
    p.add_entity(Vent(name="Exhaust", x_min=0, x_max=width,
                      y_min=0, y_max=depth, z_min=height, z_max=height,
                      surface_id="OPEN"))
    # Thermocouple tree
    for z in [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]:
        p.add_entity(Device(name=f"TC_z{z}", quantity="TEMPERATURE",
                             x=cx, y=cy, z=z))
    p.add_entity(Slice(name="SLCF_Y_MID", quantity="TEMPERATURE",
                        plane="Y", position=cy))
    p.add_entity(BoundaryFile(name="BNDF_WALL_T", quantity="WALL TEMPERATURE"))
    return p


def _build_wildland_fire(
    *,
    chid: str = "wildland_fire",
    t_end: float = 60.0,
    wind_speed: float = 5.0,
    domain_x: float = 50.0,
    domain_y: float = 20.0,
    domain_z: float = 10.0,
    cell_size: float = 0.2,
    **_,
) -> FdsProject:
    p = FdsProject()
    p.chid = chid
    p.title = f"Wildland fire — wind={wind_speed} m/s"
    p.params.t_end = t_end
    p.misc.u0 = wind_speed

    nx, ny, nz = _auto_cells(domain_x, domain_y, domain_z, cell_size)
    p.add_entity(Mesh(name="Domain", x_min=0, x_max=domain_x,
                      y_min=0, y_max=domain_y, z_min=0, z_max=domain_z,
                      cell_count=(nx, ny, nz)))
    p.add_entity(Reaction(name="GRASS", fuel="ETHYLENE",
                          heat_of_combustion=43000.0, soot_yield=0.015))
    p.add_entity(Surface(name="GrassIgniter", heat_release_rate=200.0, tau_q=2.0))
    # Wind inflow BC
    p.add_entity(Vent(name="WindInlet", x_min=0, x_max=0,
                      y_min=0, y_max=domain_y, z_min=0, z_max=domain_z,
                      surface_id="OPEN"))
    p.add_entity(Vent(name="WindOutlet", x_min=domain_x, x_max=domain_x,
                      y_min=0, y_max=domain_y, z_min=0, z_max=domain_z,
                      surface_id="OPEN"))
    p.add_entity(Vent(name="Top", x_min=0, x_max=domain_x,
                      y_min=0, y_max=domain_y,
                      z_min=domain_z, z_max=domain_z, surface_id="OPEN"))
    # Velocity and temperature probes
    for x in [5.0, 15.0, 30.0, 45.0]:
        p.add_entity(Device(name=f"U_{x}m", quantity="U-VELOCITY",
                             x=x, y=domain_y / 2, z=2.0))
        p.add_entity(Device(name=f"T_{x}m", quantity="TEMPERATURE",
                             x=x, y=domain_y / 2, z=2.0))
    p.add_entity(Slice(name="SLCF_Y_MID", quantity="TEMPERATURE",
                        plane="Y", position=domain_y / 2, vector=True))
    return p


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_default_engine = PresetEngine()


def list_presets() -> List[str]:
    """Return the names of all registered built-in templates."""
    return _default_engine.names()


def apply_preset(name: str, **kwargs) -> FdsProject:
    """Apply a named preset using the default engine."""
    return _default_engine.apply(name, **kwargs)
