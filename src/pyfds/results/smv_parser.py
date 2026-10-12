"""
PyFDS SMV Metadata Parser
==========================
Parses the ``.smv`` metadata file produced by FDS, extracting mesh
geometry, linked output files, and visualization object descriptors.

Supported sections
------------------
GRID / PDIM / TRNX / TRNY / TRNZ   — mesh geometry
SLCF                                — slice file references
BNDF                                — boundary file references
ISOF                                — isosurface file references
PL3D                                — Plot3D file references
DEVICE / SMOKEDEVICE                — device/sensor locations
PART                                — particle file references
S3D                                 — smoke-3D file references
OFFSET / VIEWPOINT                  — camera/scene settings

Example::

    from pyfds.results.smv_parser import SmvParser

    meta = SmvParser().parse("case.smv")
    print(meta.grids)
    print(meta.slices)
    print(meta.devices)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SmvGrid:
    """One FDS mesh as represented in the SMV file."""
    mesh_id: int                      # 1-based mesh index
    chid: str = ""
    n_cells: Tuple[int, int, int] = (0, 0, 0)   # (nx, ny, nz)
    extents: Tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # xlo,xhi,ylo,yhi,zlo,zhi
    x_coords: List[float] = field(default_factory=list)
    y_coords: List[float] = field(default_factory=list)
    z_coords: List[float] = field(default_factory=list)


@dataclass
class SmvSlice:
    """Reference to a ``*.sf`` slice file in the SMV."""
    filepath: str
    mesh_id: int
    quantity: str
    short_name: str
    units: str
    i1: int = 0; i2: int = 0
    j1: int = 0; j2: int = 0
    k1: int = 0; k2: int = 0
    cell_centred: bool = False

    @property
    def is_2d(self) -> bool:
        return (self.i1 == self.i2 or
                self.j1 == self.j2 or
                self.k1 == self.k2)


@dataclass
class SmvBoundary:
    """Reference to a ``*.bf`` boundary file in the SMV."""
    filepath: str
    mesh_id: int
    quantity: str
    short_name: str
    units: str


@dataclass
class SmvIsosurface:
    """Reference to a ``*.iso`` / ``*.ge1`` isosurface file."""
    filepath: str
    mesh_id: int
    quantity: str
    short_name: str
    units: str
    level: float = 0.0


@dataclass
class SmvPlot3D:
    """Reference to a ``*.q`` Plot3D file."""
    filepath: str
    mesh_id: int
    quantities: List[str] = field(default_factory=list)   # up to 5


@dataclass
class SmvSmoke3D:
    """Reference to a ``*.s3d`` smoke-3D file."""
    filepath: str
    mesh_id: int
    quantity: str
    short_name: str
    units: str


@dataclass
class SmvParticle:
    """Reference to a particle ``*.prt5`` file."""
    filepath: str
    mesh_id: int
    n_classes: int = 0


@dataclass
class SmvDevice:
    """A device/sensor recorded in the SMV."""
    name: str
    quantity: str = ""
    units: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    orientation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    state: str = ""


@dataclass
class SmvViewpoint:
    """A named camera viewpoint read from the SMV file."""
    name: str
    eye: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    up: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    zoom: float = 1.0


@dataclass
class SmvSurface:
    """A surface display record from the SMV file."""
    surface_id: str
    rgb: Tuple[int, int, int] = (128, 128, 128)
    transparency: float = 0.0


@dataclass
class SmvMetadata:
    """All metadata extracted from a ``.smv`` file."""
    smv_filepath: str
    chid: str = ""
    fds_version: str = ""
    title: str = ""
    grids: List[SmvGrid] = field(default_factory=list)
    slices: List[SmvSlice] = field(default_factory=list)
    boundaries: List[SmvBoundary] = field(default_factory=list)
    isosurfaces: List[SmvIsosurface] = field(default_factory=list)
    plot3d: List[SmvPlot3D] = field(default_factory=list)
    smoke3d: List[SmvSmoke3D] = field(default_factory=list)
    particles: List[SmvParticle] = field(default_factory=list)
    devices: List[SmvDevice] = field(default_factory=list)
    viewpoints: List[SmvViewpoint] = field(default_factory=list)
    surfaces: List[SmvSurface] = field(default_factory=list)
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    raw_sections: Dict[str, List[List[str]]] = field(default_factory=dict)

    def slice_quantities(self) -> List[str]:
        return list({s.quantity for s in self.slices})

    def boundary_quantities(self) -> List[str]:
        return list({b.quantity for b in self.boundaries})


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class SmvParser:
    """
    Parses a FDS ``.smv`` file into ``SmvMetadata``.

    The SMV format is line-oriented with keyword/section blocks.
    This parser does a single forward pass, accumulating sections by
    keyword and then dispatching to typed handlers.
    """

    def parse(self, filepath: str) -> SmvMetadata:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"SMV file not found: {filepath}")

        meta = SmvMetadata(smv_filepath=str(path))
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

        self._first_pass(lines, meta)
        logger.info("SmvParser: %s  grids=%d  slices=%d  bndf=%d  devices=%d",
                    filepath, len(meta.grids), len(meta.slices),
                    len(meta.boundaries), len(meta.devices))
        return meta

    # ── First-pass dispatcher ─────────────────────────────────────────────────

    def _first_pass(self, lines: List[str], meta: SmvMetadata) -> None:
        i = 0
        n = len(lines)
        mesh_count = 0

        while i < n:
            raw = lines[i].rstrip()
            token = raw.strip().upper()
            i += 1

            if token.startswith("CHID"):
                meta.chid = raw.split(None, 1)[1].strip() if len(raw.split()) > 1 else ""
            elif token.startswith("TITLE"):
                meta.title = raw.split(None, 1)[1].strip() if len(raw.split()) > 1 else ""
            elif token.startswith("VERSION"):
                meta.fds_version = raw.split(None, 1)[1].strip() if len(raw.split()) > 1 else ""
            elif token == "GRID":
                mesh_count += 1
                i = self._parse_grid(lines, i, mesh_count, meta)
            elif token in ("SLCF", "SLCC"):
                cell_centred = token == "SLCC"
                i = self._parse_slcf(lines, i, mesh_count, cell_centred, meta)
            elif token == "BNDF":
                i = self._parse_bndf(lines, i, mesh_count, meta)
            elif token == "ISOF":
                i = self._parse_isof(lines, i, mesh_count, meta)
            elif token == "PL3D":
                i = self._parse_pl3d(lines, i, mesh_count, meta)
            elif token in ("SMOKF3D", "S3D"):
                i = self._parse_s3d(lines, i, mesh_count, meta)
            elif token == "PART":
                i = self._parse_part(lines, i, mesh_count, meta)
            elif token in ("DEVICE", "SMOKEDEVICE"):
                i = self._parse_device(lines, i, meta)
            elif token == "OFFSET":
                i = self._parse_offset(lines, i, meta)
            elif token == "VIEWPOINT":
                i = self._parse_viewpoint(lines, i, raw, meta)
            elif token in ("TRNX", "TRNY", "TRNZ"):
                axis = token[-1].lower()   # 'x', 'y', or 'z'
                i = self._parse_trn(lines, i, axis, mesh_count, meta)
            elif token == "SURFACE":
                i = self._parse_surface_record(lines, i, meta)
            # else: skip unknown tokens

    # ── Section parsers ───────────────────────────────────────────────────────

    def _parse_grid(self, lines: List[str], i: int, mesh_id: int, meta: SmvMetadata) -> int:
        grid = SmvGrid(mesh_id=mesh_id)
        # Next line: nx ny nz
        if i < len(lines):
            parts = lines[i].split(); i += 1
            if len(parts) >= 3:
                grid.n_cells = (int(parts[0]), int(parts[1]), int(parts[2]))
        # Skip PDIM block if present (PDIM keyword + extents line)
        while i < len(lines):
            tok = lines[i].strip().upper()
            if tok == "PDIM":
                i += 1
                if i < len(lines):
                    p = lines[i].split(); i += 1
                    if len(p) >= 6:
                        grid.extents = tuple(float(v) for v in p[:6])
                break
            elif tok in ("TRNX", "TRNY", "TRNZ", "GRID", "SLCF", "SLCC",
                         "BNDF", "ISOF", "PL3D", "PART", "DEVICE",
                         "SMOKEDEVICE", "OFFSET", "S3D", "SMOKF3D",
                         "CHID", "TITLE", "VERSION", ""):
                break
            i += 1
        meta.grids.append(grid)
        return i

    def _next_nonempty(self, lines: List[str], i: int) -> Tuple[str, int]:
        while i < len(lines):
            s = lines[i].strip()
            if s:
                return s, i + 1
            i += 1
        return "", i

    def _parse_slcf(self, lines: List[str], i: int, mesh_id: int,
                    cell_centred: bool, meta: SmvMetadata) -> int:
        # Line 1: filename
        fn, i = self._next_nonempty(lines, i)
        if not fn:
            return i
        # Line 2: quantity short_name units
        qty_line, i = self._next_nonempty(lines, i)
        parts = qty_line.split(None, 2)
        quantity   = parts[0] if len(parts) > 0 else ""
        short_name = parts[1] if len(parts) > 1 else ""
        units      = parts[2] if len(parts) > 2 else ""
        # Line 3: i1 i2 j1 j2 k1 k2
        idx_line, i = self._next_nonempty(lines, i)
        idx = idx_line.split()
        i1=j1=k1=0; i2=j2=k2=0
        if len(idx) >= 6:
            i1,i2,j1,j2,k1,k2 = (int(v) for v in idx[:6])
        meta.slices.append(SmvSlice(
            filepath=fn, mesh_id=mesh_id,
            quantity=quantity, short_name=short_name, units=units,
            i1=i1, i2=i2, j1=j1, j2=j2, k1=k1, k2=k2,
            cell_centred=cell_centred,
        ))
        return i

    def _parse_bndf(self, lines: List[str], i: int, mesh_id: int, meta: SmvMetadata) -> int:
        fn,  i = self._next_nonempty(lines, i)
        if not fn:
            return i
        qty_line, i = self._next_nonempty(lines, i)
        parts = qty_line.split(None, 2)
        quantity   = parts[0] if len(parts) > 0 else ""
        short_name = parts[1] if len(parts) > 1 else ""
        units      = parts[2] if len(parts) > 2 else ""
        meta.boundaries.append(SmvBoundary(
            filepath=fn, mesh_id=mesh_id,
            quantity=quantity, short_name=short_name, units=units,
        ))
        return i

    def _parse_isof(self, lines: List[str], i: int, mesh_id: int, meta: SmvMetadata) -> int:
        fn, i = self._next_nonempty(lines, i)
        if not fn:
            return i
        qty_line, i = self._next_nonempty(lines, i)
        parts = qty_line.split(None, 3)
        level      = float(parts[0]) if len(parts) > 0 else 0.0
        quantity   = parts[1] if len(parts) > 1 else ""
        short_name = parts[2] if len(parts) > 2 else ""
        units      = parts[3] if len(parts) > 3 else ""
        meta.isosurfaces.append(SmvIsosurface(
            filepath=fn, mesh_id=mesh_id,
            quantity=quantity, short_name=short_name, units=units,
            level=level,
        ))
        return i

    def _parse_pl3d(self, lines: List[str], i: int, mesh_id: int, meta: SmvMetadata) -> int:
        fn, i = self._next_nonempty(lines, i)
        if not fn:
            return i
        quantities: List[str] = []
        for _ in range(5):
            if i < len(lines):
                q = lines[i].strip()
                if q and not q.upper().startswith(("GRID","SLCF","BNDF",
                                                    "ISOF","PL3D","PART",
                                                    "DEVICE","OFFSET")):
                    quantities.append(q)
                    i += 1
                else:
                    break
        meta.plot3d.append(SmvPlot3D(filepath=fn, mesh_id=mesh_id, quantities=quantities))
        return i

    def _parse_s3d(self, lines: List[str], i: int, mesh_id: int, meta: SmvMetadata) -> int:
        fn, i = self._next_nonempty(lines, i)
        if not fn:
            return i
        qty_line, i = self._next_nonempty(lines, i)
        parts = qty_line.split(None, 2)
        quantity   = parts[0] if len(parts) > 0 else ""
        short_name = parts[1] if len(parts) > 1 else ""
        units      = parts[2] if len(parts) > 2 else ""
        meta.smoke3d.append(SmvSmoke3D(
            filepath=fn, mesh_id=mesh_id,
            quantity=quantity, short_name=short_name, units=units,
        ))
        return i

    def _parse_part(self, lines: List[str], i: int, mesh_id: int, meta: SmvMetadata) -> int:
        fn, i = self._next_nonempty(lines, i)
        if not fn:
            return i
        n_line, i = self._next_nonempty(lines, i)
        try:
            n_classes = int(n_line.split()[0])
        except (ValueError, IndexError):
            n_classes = 0
        meta.particles.append(SmvParticle(filepath=fn, mesh_id=mesh_id, n_classes=n_classes))
        return i

    def _parse_device(self, lines: List[str], i: int, meta: SmvMetadata) -> int:
        # Line 1: name
        name_line, i = self._next_nonempty(lines, i)
        name = name_line.strip()
        # Line 2: x y z  ox oy oz  quantity units
        data_line, i = self._next_nonempty(lines, i)
        parts = data_line.split()
        x = float(parts[0]) if len(parts) > 0 else 0.0
        y = float(parts[1]) if len(parts) > 1 else 0.0
        z = float(parts[2]) if len(parts) > 2 else 0.0
        ox = float(parts[3]) if len(parts) > 3 else 0.0
        oy = float(parts[4]) if len(parts) > 4 else 0.0
        oz = float(parts[5]) if len(parts) > 5 else 0.0
        quantity = parts[6] if len(parts) > 6 else ""
        units    = parts[7] if len(parts) > 7 else ""
        meta.devices.append(SmvDevice(
            name=name, quantity=quantity, units=units,
            x=x, y=y, z=z,
            orientation=(ox, oy, oz),
        ))
        return i

    def _parse_offset(self, lines: List[str], i: int, meta: SmvMetadata) -> int:
        off_line, i = self._next_nonempty(lines, i)
        parts = off_line.split()
        if len(parts) >= 3:
            meta.offset = (float(parts[0]), float(parts[1]), float(parts[2]))
        return i

    def _parse_viewpoint(self, lines: List[str], i: int,
                         header_line: str, meta: SmvMetadata) -> int:
        """
        Parse a VIEWPOINT block from the SMV file.

        Format::
          VIEWPOINT  <name>
            EYE    x y z
            TARGET x y z
            UP     x y z
            ZOOM   f
        """
        # Name may be on the same VIEWPOINT line or the next line
        name_part = header_line.strip().split(None, 1)
        name = name_part[1].strip() if len(name_part) > 1 else f"VP_{len(meta.viewpoints)}"
        if not name:
            name_line, i = self._next_nonempty(lines, i)
            name = name_line.strip()

        vp = SmvViewpoint(name=name)
        # Read sub-keys until we hit a section keyword
        _SECTION_KEYS = {"GRID","SLCF","SLCC","BNDF","ISOF","PL3D","PART",
                         "DEVICE","SMOKEDEVICE","OFFSET","S3D","SMOKF3D",
                         "CHID","TITLE","VERSION","VIEWPOINT","TRNX","TRNY",
                         "TRNZ","SURFACE"}
        while i < len(lines):
            raw = lines[i].strip()
            if not raw:
                i += 1
                continue
            tok = raw.split()[0].upper()
            if tok in _SECTION_KEYS:
                break
            parts = raw.split()
            if tok == "EYE" and len(parts) >= 4:
                vp.eye = (float(parts[1]), float(parts[2]), float(parts[3]))
            elif tok == "TARGET" and len(parts) >= 4:
                vp.target = (float(parts[1]), float(parts[2]), float(parts[3]))
            elif tok == "UP" and len(parts) >= 4:
                vp.up = (float(parts[1]), float(parts[2]), float(parts[3]))
            elif tok == "ZOOM" and len(parts) >= 2:
                try:
                    vp.zoom = float(parts[1])
                except ValueError:
                    pass
            i += 1
        meta.viewpoints.append(vp)
        return i

    def _parse_trn(self, lines: List[str], i: int, axis: str,
                   mesh_id: int, meta: SmvMetadata) -> int:
        """
        Parse TRNX/TRNY/TRNZ coordinate arrays into the appropriate grid's
        x_coords / y_coords / z_coords list.

        SMV format::
          TRNX  <mesh_index>
          <n_coords>
          coord1
          coord2
          ...
        """
        # First non-empty line: mesh index (sometimes the mesh index precedes coord count)
        idx_line, i = self._next_nonempty(lines, i)
        try:
            _mesh_idx = int(idx_line.split()[0])
        except (ValueError, IndexError):
            return i

        # Next line: number of coordinates
        n_line, i = self._next_nonempty(lines, i)
        try:
            n_coords = int(n_line.split()[0])
        except (ValueError, IndexError):
            return i

        coords: List[float] = []
        while i < len(lines) and len(coords) < n_coords:
            raw = lines[i].strip()
            i += 1
            if not raw:
                continue
            # Stop on any uppercase section keyword
            if raw.split()[0].upper() in {"GRID","SLCF","SLCC","BNDF","ISOF",
                                            "PL3D","PART","DEVICE","SMOKEDEVICE",
                                            "OFFSET","S3D","SMOKF3D","TRNX","TRNY",
                                            "TRNZ","VIEWPOINT","SURFACE"}:
                i -= 1
                break
            try:
                coords.append(float(raw.split()[0]))
            except ValueError:
                pass

        # Attach to the matching grid
        grid = next((g for g in meta.grids if g.mesh_id == _mesh_idx), None)
        if grid is None and meta.grids:
            grid = meta.grids[-1]
        if grid is not None:
            if axis == "x":
                grid.x_coords = coords
            elif axis == "y":
                grid.y_coords = coords
            else:
                grid.z_coords = coords
        return i

    def _parse_surface_record(self, lines: List[str], i: int,
                               meta: SmvMetadata) -> int:
        """
        Parse a SURFACE display record from the SMV file.

        Format::
          SURFACE <surface_id>
          r g b
          <transparency>
        """
        id_line, i = self._next_nonempty(lines, i)
        surface_id = id_line.strip()
        rgb = (128, 128, 128)
        transparency = 0.0

        color_line, i = self._next_nonempty(lines, i)
        try:
            parts = color_line.split()
            rgb = (int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            pass

        # Optional transparency line
        if i < len(lines):
            t_raw = lines[i].strip()
            if t_raw and not t_raw.split()[0].upper() in {
                    "GRID","SLCF","SLCC","BNDF","ISOF","PL3D","PART",
                    "DEVICE","SMOKEDEVICE","OFFSET","S3D","SMOKF3D",
                    "TRNX","TRNY","TRNZ","VIEWPOINT","SURFACE"}:
                try:
                    transparency = float(t_raw.split()[0])
                    i += 1
                except ValueError:
                    pass

        meta.surfaces.append(SmvSurface(
            surface_id=surface_id, rgb=rgb, transparency=transparency,
        ))
        return i
