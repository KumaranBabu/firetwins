"""
Builds pyvista mesh geometry from the current ``FdsApi`` project state.

Pure data/geometry logic only — no Qt widget, no VTK render window, no
display/OpenGL context required anywhere in this module. Constructing
``pyvista`` mesh objects (``pv.Box``, ``pv.Sphere``, ...) is just numpy-array
bookkeeping and is always safe, headless or not. Fully unit-testable.

The actual embedding (``pyvistaqt.QtInteractor``) lives in
``viewport_3d.py`` and is deliberately kept thin: it calls ``build_scene()``
then hands each ``ActorSpec`` to the plotter. That split exists because
``QtInteractor`` needs a real OpenGL-capable native window handle, which
Qt's offscreen QPA platform cannot provide — attempting it there is not a
catchable Python exception, it's a native access violation that kills the
whole process. So the widget can only be verified by a live desktop launch;
this module carries all the logic that a headless test suite *can* cover.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import pyvista as pv

from pyfds.core.viewport import VisibilityFlags

# A small, deliberately incomplete map covering the common FDS/PyroSim named
# colors used as Obstruction/Vent .color string values; anything unmapped
# (a hex string, a typo, an unlisted name) falls back to neutral gray rather
# than erroring — this is visualization, not validation.
_COLOR_MAP = {
    "GRAY": "#9a9a9a", "GREY": "#9a9a9a",
    "RED": "#c0392b", "GREEN": "#2e8b57", "BLUE": "#3060c0",
    "YELLOW": "#d4ac0d", "ORANGE": "#d4720a", "WHITE": "#e8e8e8",
    "BLACK": "#222222", "BROWN": "#8b5a2b", "PURPLE": "#7d3c98",
}

_DEFAULT_COLOR = "#9a9a9a"
_MESH_COLOR = "#4a90d9"
_VENT_COLOR = "#2e8b57"
_HOLE_COLOR = "#c0392b"
_DEVICE_COLOR = "#d4ac0d"
_INIT_COLOR = "#1abc9c"
_PROFILE_COLOR = "#9b59b6"
_GEOM_COLOR = "#8899a6"
_SLICE_COLOR = "#e67e22"


def _color(name: Optional[str]) -> str:
    if not isinstance(name, str) or not name:
        return _DEFAULT_COLOR
    if name.startswith("#"):
        return name
    return _COLOR_MAP.get(name.upper(), _DEFAULT_COLOR)


@dataclass
class ActorSpec:
    """One thing to add to the plotter, and how to draw it."""
    mesh: "pv.DataSet"
    color: str
    style: str = "surface"   # "surface" | "wireframe"
    opacity: float = 1.0
    label: str = ""
    entity_kind: str = ""    # "mesh" | "obstruction" | "vent" | "hole" | "device"
    edges: bool = False      # draw the object's edges on top of its faces (render mode "outlines")
    smooth: bool = False     # smooth shading (render mode "realistic")
    helper: bool = False     # decoration (grid lines, shells): not an entity, so never picked
    # manager_attr/entity let a picked actor resolve back to exactly the
    # (attr, entity) pair ProjectExplorer.selected() returns, so viewport
    # click-to-select can drive the same tree-selection-based handlers
    # (Delete Selected, Edit Properties, the right-click menu) with no
    # separate code path.
    manager_attr: str = ""
    entity: Any = None


FIELD_DATA_KEY = "pyfds_entity_key"


def entity_key(manager_attr: str, entity: Any) -> str:
    """Stable string key identifying one entity.

    Stored in each mesh's VTK ``field_data`` (see ``build_scene``) so a
    picked mesh can resolve back to its ``(manager_attr, entity)`` pair
    even when pyvista/VTK hands the picking callback a different Python
    wrapper object than the one ``build_scene()`` originally created —
    confirmed empirically that a raw ``id()`` match across the picker
    boundary is not reliable. ``field_data`` travels with the underlying
    VTK dataset itself, unlike a transient Python attribute, so this is
    safe regardless of wrapper identity.
    """
    return f"{manager_attr}:{id(entity)}"


def _thicken(bounds: Tuple[float, ...], eps: float = 1e-3) -> Tuple[float, ...]:
    b = list(bounds)
    for i in range(3):
        if b[2 * i + 1] - b[2 * i] < eps:
            b[2 * i + 1] = b[2 * i] + eps
    return tuple(b)


def _box_from_bbox(entity) -> Optional["pv.PolyData"]:
    """Build a pyvista box from an FdsEntity's bbox(), thickening any
    degenerate axis (a vent/hole flush with a wall has z_min==z_max, say)
    so it stays visible instead of collapsing to zero volume."""
    bounds = entity.bbox()
    if bounds is None:
        return None
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    eps = 1e-3
    if xmax - xmin < eps:
        xmax = xmin + eps
    if ymax - ymin < eps:
        ymax = ymin + eps
    if zmax - zmin < eps:
        zmax = zmin + eps
    return pv.Box(bounds=(xmin, xmax, ymin, ymax, zmin, zmax))


def mesh_grid_lines(mesh: Any, max_per_axis: int = 120) -> "pv.PolyData":
    """The cell lines on the six faces of one solution mesh (every cell boundary; for very fine meshes every n-th
    one, so at most *max_per_axis* lines per direction are drawn)."""
    lo = (mesh.x_min, mesh.y_min, mesh.z_min)
    hi = (mesh.x_max, mesh.y_max, mesh.z_max)
    ticks = []
    for i in range(3):
        n = max(1, int(mesh.cell_count[i]))
        step = max(1, math.ceil(n / max_per_axis))
        idx = sorted(set(list(range(0, n + 1, step)) + [n]))
        ticks.append([lo[i] + (hi[i] - lo[i]) * k / n for k in idx])
    points: List[Tuple[float, float, float]] = []
    lines: List[int] = []

    def seg(a, b):
        lines.extend([2, len(points), len(points) + 1])
        points.extend([a, b])

    for fixed, (u, v) in ((0, (1, 2)), (1, (0, 2)), (2, (0, 1))):
        for plane in (lo[fixed], hi[fixed]):
            for tu in ticks[u]:                       # lines along v at each u
                a, b = [0.0] * 3, [0.0] * 3
                a[fixed] = b[fixed] = plane
                a[u] = b[u] = tu
                a[v], b[v] = lo[v], hi[v]
                seg(tuple(a), tuple(b))
            for tv in ticks[v]:                       # lines along u at each v
                a, b = [0.0] * 3, [0.0] * 3
                a[fixed] = b[fixed] = plane
                a[v] = b[v] = tv
                a[u], b[u] = lo[u], hi[u]
                seg(tuple(a), tuple(b))
    poly = pv.PolyData()
    poly.points = points
    poly.lines = lines
    return poly


def slice_bounds(slc: Any, extent: Optional[Tuple[float, ...]]) -> Optional[Tuple[float, ...]]:
    """Where a slice plane sits: its own XB, or the model extent cut at ``position`` on its ``plane`` axis."""
    if getattr(slc, "xb", None):
        return tuple(slc.xb)
    if extent is None:
        return None
    b = list(extent)
    letter = str(slc.plane).upper()[:1]
    axis = "XYZ".index(letter) if letter in ("X", "Y", "Z") else 0
    b[2 * axis] = b[2 * axis + 1] = float(slc.position)
    return tuple(b)


def build_scene(api: Any) -> List[ActorSpec]:
    """One ``ActorSpec`` per currently-visible entity in the active project.

    Reads ``api.viewport.state`` for visibility flags and the global
    wireframe override, so a GUI toggle or an agent tool call
    (``api.viewport.set_visibility(...)``/``toggle_wireframe()``) changes
    what gets built here without this function needing its own state.
    """
    state = api.viewport.state
    mode = getattr(state, "render_mode", "solid")
    wireframe = state.show_wireframe or mode == "wireframe"
    specs: List[ActorSpec] = []

    def style(default: str) -> str:
        return "wireframe" if wireframe else default

    def finish(spec: ActorSpec) -> ActorSpec:
        spec.edges = mode == "outlines" and spec.style == "surface"
        spec.smooth = mode == "realistic"
        return spec

    def enabled(entities):
        # A disabled entity is excluded from the FDS write entirely (see
        # io/fds_writer.py) — the 3D view should match what will actually
        # be simulated, not show clutter that's effectively already deleted.
        return [e for e in entities if getattr(e, "enabled", True)]

    display = getattr(state, "mesh_display", "outline")
    if state.is_visible(VisibilityFlags.MESHES) and display != "hidden":
        for mesh in enabled(api.meshes.all()):
            box = _box_from_bbox(mesh)
            if box is not None:
                # Mesh boundaries are always wireframe, never solid-filled —
                # a solid box would hide everything inside the domain.
                specs.append(ActorSpec(box, _MESH_COLOR, style="wireframe",
                                        label=mesh.name, entity_kind="mesh",
                                        manager_attr="meshes", entity=mesh))
                if display == "boundary":              # the faces as a faint shell, so the domain reads as a volume
                    specs.append(ActorSpec(box.copy(), _MESH_COLOR, opacity=0.08, label=mesh.name,
                                           entity_kind="mesh-shell", helper=True))
                elif display == "lines":
                    specs.append(ActorSpec(mesh_grid_lines(mesh), _MESH_COLOR, style="wireframe", opacity=0.55,
                                           label=mesh.name, entity_kind="mesh-lines", helper=True))

    if state.is_visible(VisibilityFlags.OBSTRUCTIONS):
        for obst in enabled(api.obstructions.all()):
            box = _box_from_bbox(obst)
            if box is not None:
                # FDS TRANSPARENCY is opacity (1.0=opaque); 0.0 is the "unset"
                # default and means "use FDS's own opaque default" — not 0% opacity.
                opacity = obst.transparency if obst.transparency else 1.0
                specs.append(finish(ActorSpec(box, _color(obst.color), style=style("surface"),
                                              opacity=opacity, label=obst.name, entity_kind="obstruction",
                                              manager_attr="obstructions", entity=obst)))

    if state.is_visible(VisibilityFlags.HOLES):
        for hole in enabled(api.holes.all()):
            hbox = _box_from_bbox(hole)
            if hbox is not None:
                specs.append(ActorSpec(hbox, _HOLE_COLOR, style="wireframe",
                                        label=hole.name, entity_kind="hole",
                                        manager_attr="holes", entity=hole))

    if state.is_visible(VisibilityFlags.VENTS):
        for vent in enabled(api.vents.all()):
            box = _box_from_bbox(vent)
            if box is not None:
                opacity = vent.transparency if vent.transparency else 0.55
                specs.append(finish(ActorSpec(box, _VENT_COLOR, style=style("surface"),
                                              opacity=opacity, label=vent.name, entity_kind="vent",
                                              manager_attr="vents", entity=vent)))

    if state.is_visible(VisibilityFlags.DEVICES):
        for device in enabled(api.devices.all()):
            xyz = getattr(device, "xyz", None)
            if xyz is not None:
                specs.append(ActorSpec(pv.Sphere(radius=0.08, center=tuple(xyz)), _DEVICE_COLOR,
                                        label=device.name, entity_kind="device",
                                        manager_attr="devices", entity=device))

    if state.is_visible(VisibilityFlags.INIT_REGIONS):
        # &INIT regions (including particle-cloud INITs, which just add
        # part_id/n_particles on the same entity) are a real spatial volume,
        # same shape as Obstruction/Vent — shown translucent so they read as
        # a "condition zone" rather than solid geometry.
        for init in enabled(api.inits.all()):
            box = _box_from_bbox(init)
            if box is not None:
                specs.append(ActorSpec(box, _INIT_COLOR, style=style("surface"), opacity=0.3,
                                        label=init.name, entity_kind="init",
                                        manager_attr="inits", entity=init))

    if state.is_visible(VisibilityFlags.PROFILES):
        # &PROF points, like devices, mark a single measurement location —
        # no separate namelist geometry to draw, just the point itself.
        for prof in enabled(api.profs.all()):
            xyz = (getattr(prof, "x", None), getattr(prof, "y", None), getattr(prof, "z", None))
            if None not in xyz:
                specs.append(ActorSpec(pv.Sphere(radius=0.08, center=xyz), _PROFILE_COLOR,
                                        label=prof.name, entity_kind="profile",
                                        manager_attr="profs", entity=prof))

    if state.is_visible(VisibilityFlags.GEOMETRY):
        # &GEOM entities (parametric primitives from GeometryTools — Draw >
        # Sphere/Cylinder/Cone — or an imported STL) carry their own
        # triangle mesh (verts/faces) rather than an XB box, so they build
        # a real PolyData instead of going through _box_from_bbox().
        for geom in enabled(api.geom.all()):
            if not geom.verts or not geom.faces:
                continue
            # PyVista's flat face format: each triangle is [3, i0, i1, i2].
            flat_faces: List[int] = []
            for face in geom.faces:
                flat_faces.append(len(face))
                flat_faces.extend(face)
            mesh = pv.PolyData(geom.verts, flat_faces)
            specs.append(ActorSpec(mesh, _GEOM_COLOR, style=style("surface"),
                                    label=geom.name, entity_kind="geom",
                                    manager_attr="geom", entity=geom))

    if state.is_visible(VisibilityFlags.SLICES):
        extent = scene_bbox(api)
        for slc in enabled(api.slices.all()):
            bounds = slice_bounds(slc, extent)
            if bounds is not None:
                specs.append(ActorSpec(pv.Box(bounds=_thicken(bounds)), _SLICE_COLOR, opacity=0.22, label=slc.name,
                                       entity_kind="slice", manager_attr="slices", entity=slc))

    # Particle classes (&PART) have no location of their own — they're
    # referenced by name from an Init's part_id or a Device's prop_id, so
    # there is nothing spatial to draw for them here.

    # Tag every mesh's VTK field_data with its lookup key (see entity_key())
    # in one place, rather than repeating it in every branch above.
    for spec in specs:
        if spec.entity is not None:
            spec.mesh.field_data[FIELD_DATA_KEY] = [entity_key(spec.manager_attr, spec.entity)]

    return specs


def scene_bbox(api: Any) -> Optional[Tuple[float, float, float, float, float, float]]:
    """Union bounding box of everything build_scene() would draw geometry for.

    Used to frame the camera on a standard-view preset — a fixed camera
    distance would put a 2m room and a 200m tunnel at the same arbitrary
    zoom, so presets scale to the actual model extent instead.
    """
    boxes = []
    for attr in ("meshes", "obstructions", "vents", "holes", "devices", "inits", "profs", "geom"):
        manager = getattr(api, attr, None)
        if manager is None:
            continue
        for entity in manager.all():
            b = entity.bbox()
            if b is not None:
                boxes.append(b)
    if not boxes:
        return None
    xs = [v for b in boxes for v in (b[0], b[1])]
    ys = [v for b in boxes for v in (b[2], b[3])]
    zs = [v for b in boxes for v in (b[4], b[5])]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))


def preset_distance(api: Any, default: float = 15.0) -> float:
    """A camera distance scaled to the current scene, for framing a preset view."""
    bbox = scene_bbox(api)
    if bbox is None:
        return default
    diagonal = math.sqrt(
        (bbox[1] - bbox[0]) ** 2 + (bbox[3] - bbox[2]) ** 2 + (bbox[5] - bbox[4]) ** 2
    )
    return max(diagonal * 1.2, 2.0)
