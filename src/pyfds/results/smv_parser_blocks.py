"""SmvParser: grid, slice, boundary, isosurface, Plot3D, smoke, particle, device blocks."""
from __future__ import annotations

from typing import List, Tuple

from .smv_parser_model import (
    SmvBoundary,
    SmvDevice,
    SmvGrid,
    SmvIsosurface,
    SmvMetadata,
    SmvParticle,
    SmvPlot3D,
    SmvSlice,
    SmvSmoke3D,
)


class SmvParserBlocksMixin:
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
