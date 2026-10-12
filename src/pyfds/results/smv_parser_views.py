"""SmvParser: viewpoints, terrain and surface records."""
from __future__ import annotations

from typing import List

from .smv_parser_model import (
    SmvMetadata,
    SmvSurface,
    SmvViewpoint,
)


class SmvParserViewsMixin:
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
