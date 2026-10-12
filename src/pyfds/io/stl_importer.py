"""
PyFDS STL Geometry Importer
============================
Parses ASCII and binary STL files into ``Geom`` domain entities.

Supports:
  - Binary STL (little-endian, standard 50-byte triangle records)
  - ASCII STL  (``solid / facet normal / vertex / endloop`` format)
  - Auto-detection based on file content

Usage::

    from pyfds.io.stl_importer import StlImporter

    geom = StlImporter.load("building.stl", surf_id="CONCRETE")
    geom.name = "building_shell"
    project.add_entity(geom)
"""
from __future__ import annotations

import logging
import os
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Vertex tolerance for deduplication (metres)
_WELD_TOL = 1e-7


class StlImporter:
    """
    Load an STL file and return a :class:`~pyfds.domain.model.Geom` entity.

    Both ASCII and binary STL formats are supported.  Vertices are
    welded (de-duplicated) so the resulting mesh shares vertex indices
    across triangles — required for FDS &GEOM.
    """

    @staticmethod
    def load(
        path: str,
        *,
        surf_id: str = "INERT",
        surf_ids: Optional[List[str]] = None,
        name: Optional[str] = None,
        weld: bool = True,
        scale: float = 1.0,
        translate: Optional[Tuple[float, float, float]] = None,
    ) -> "Geom":  # noqa: F821
        """
        Parse *path* and return a ``Geom`` entity.

        Parameters
        ----------
        path : str
            Path to the ``.stl`` file.
        surf_id : str
            Surface ID applied to all triangles (default ``"INERT"``).
        surf_ids : list[str], optional
            Per-triangle surface IDs (length must equal number of triangles).
        name : str, optional
            Name for the Geom entity.  Defaults to the stem of *path*.
        weld : bool
            Merge coincident vertices.  Recommended; disable only for
            debugging mismatched meshes.
        scale : float
            Uniform scale factor applied to all coordinates (e.g. 0.001
            to convert mm → m).
        translate : (dx, dy, dz), optional
            Translation applied *after* scaling.

        Returns
        -------
        Geom
        """
        from pyfds.domain.model import Geom

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"STL file not found: {path}")

        entity_name = name or path.stem

        raw_verts, faces = StlImporter._parse(path)

        if scale != 1.0:
            raw_verts = [(x * scale, y * scale, z * scale) for x, y, z in raw_verts]
        if translate:
            dx, dy, dz = translate
            raw_verts = [(x + dx, y + dy, z + dz) for x, y, z in raw_verts]

        if weld:
            verts, faces = StlImporter._weld(raw_verts, faces)
        else:
            verts = raw_verts

        logger.info(
            "StlImporter: loaded %r — %d verts, %d faces",
            path.name, len(verts), len(faces),
        )

        geom = Geom(
            name=entity_name,
            surf_id=surf_id,
            surf_ids=surf_ids,
            verts=verts,
            faces=faces,
        )
        return geom

    # ── Parsers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse(path: Path) -> Tuple[List[Tuple[float, float, float]],
                                    List[Tuple[int, int, int]]]:
        """Dispatch to binary or ASCII parser; return (raw_verts, faces)."""
        with open(path, "rb") as fh:
            header = fh.read(80)

        # Binary STL starts with an 80-byte header (NOT the word "solid")
        # ASCII STL starts with "solid " (case-insensitive)
        is_ascii = False
        try:
            decoded = header[:5].decode("ascii", errors="replace").strip().lower()
            is_ascii = decoded.startswith("solid")
        except Exception:
            pass

        # Confirm ASCII: binary files beginning with "solid" still exist
        if is_ascii:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                if "facet normal" in text.lower():
                    return StlImporter._parse_ascii(text)
            except Exception:
                pass  # fall through to binary

        return StlImporter._parse_binary(path)

    @staticmethod
    def _parse_binary(path: Path) -> Tuple[List, List]:
        """Parse binary STL."""
        verts: List[Tuple[float, float, float]] = []
        faces: List[Tuple[int, int, int]] = []

        with open(path, "rb") as fh:
            fh.read(80)  # header
            n_tri_data = fh.read(4)
            if len(n_tri_data) < 4:
                raise ValueError(f"Truncated binary STL: {path}")
            n_tri = struct.unpack_from("<I", n_tri_data)[0]
            vi = 0
            for _ in range(n_tri):
                record = fh.read(50)
                if len(record) < 50:
                    break
                # 12 bytes normal (skip), then 3×12-byte vertices, 2-byte attr (skip)
                ax, ay, az = struct.unpack_from("<fff", record, 0)   # noqa
                v0 = struct.unpack_from("<fff", record, 12)
                v1 = struct.unpack_from("<fff", record, 24)
                v2 = struct.unpack_from("<fff", record, 36)
                verts.extend([v0, v1, v2])
                faces.append((vi, vi + 1, vi + 2))
                vi += 3

        return verts, faces

    @staticmethod
    def _parse_ascii(text: str) -> Tuple[List, List]:
        """Parse ASCII STL text."""
        verts: List[Tuple[float, float, float]] = []
        faces: List[Tuple[int, int, int]] = []
        vi = 0

        lines = iter(text.splitlines())
        for line in lines:
            line = line.strip().lower()
            if line.startswith("facet normal"):
                # Next is "outer loop"
                try:
                    next(lines)  # outer loop
                    tri: List[Tuple[float, float, float]] = []
                    for _ in range(3):
                        vline = next(lines).strip().lower()
                        if vline.startswith("vertex"):
                            parts = vline.split()
                            tri.append((float(parts[1]), float(parts[2]), float(parts[3])))
                    if len(tri) == 3:
                        verts.extend(tri)
                        faces.append((vi, vi + 1, vi + 2))
                        vi += 3
                except StopIteration:
                    break

        return verts, faces

    # ── Vertex welding ────────────────────────────────────────────────────────

    @staticmethod
    def _weld(
        raw_verts: List[Tuple[float, float, float]],
        raw_faces: List[Tuple[int, int, int]],
        tol: float = _WELD_TOL,
    ) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int, int]]]:
        """
        Merge vertices within *tol* of each other.

        Uses a quantisation grid for O(n) performance on typical meshes.
        """
        grid_size = max(tol, 1e-9)
        quantise = lambda c: tuple(round(x / grid_size) for x in c)

        index_map: Dict[tuple, int] = {}
        unique_verts: List[Tuple[float, float, float]] = []
        remap: List[int] = []

        for v in raw_verts:
            key = quantise(v)
            if key not in index_map:
                index_map[key] = len(unique_verts)
                unique_verts.append(v)
            remap.append(index_map[key])

        new_faces: List[Tuple[int, int, int]] = []
        for f in raw_faces:
            a, b, c = remap[f[0]], remap[f[1]], remap[f[2]]
            if a != b and b != c and a != c:   # skip degenerate triangles
                new_faces.append((a, b, c))

        return unique_verts, new_faces

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def bounds(geom: "Geom") -> Tuple[  # noqa: F821
        Tuple[float, float],
        Tuple[float, float],
        Tuple[float, float],
    ]:
        """
        Return ``((xmin,xmax),(ymin,ymax),(zmin,zmax))`` of a Geom's vertices.
        """
        if not geom.verts:
            return (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)
        xs = [v[0] for v in geom.verts]
        ys = [v[1] for v in geom.verts]
        zs = [v[2] for v in geom.verts]
        return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))

    @staticmethod
    def vertex_count(geom: "Geom") -> int:
        return len(geom.verts) if geom.verts else 0

    @staticmethod
    def face_count(geom: "Geom") -> int:
        return len(geom.faces) if geom.faces else 0
