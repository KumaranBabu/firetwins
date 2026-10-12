"""
PyFDS TetGen Engine Adapter
============================
Adapter for the TetGen tetrahedral mesh generator via its command-line binary.

Binary location (searched in order):
  1. ``TETGEN_EXE`` environment variable
  2. ``C:\\bin\\tetgen.exe``  (default Windows installation)
  3. ``tetgen`` / ``tetgen.exe`` anywhere on PATH

TetGen takes a closed triangulated surface and produces a constrained
Delaunay tetrahedral volume mesh.

License note: TetGen is dual-licensed — free for non-commercial research;
commercial use requires a separate license from Weierstrass Institute.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np

from ..base import (
    ElementType, EngineCapabilities, FileGeometry, LicenseType,
    MeshData, MeshResult, MeshingEngineBase,
    SurfaceMeshGeometry, VolumeMeshRequest,
)

logger = logging.getLogger(__name__)

_DEFAULT_WIN_PATH = Path(r"C:\bin\tetgen.exe")
_BINARY_NAMES = ["tetgen", "tetgen.exe"]


def _find_tetgen_exe() -> Optional[Path]:
    """Return the path to the tetgen binary, or None if not found."""
    env = os.environ.get("TETGEN_EXE")
    if env:
        p = Path(env)
        if p.is_file():
            return p

    if _DEFAULT_WIN_PATH.is_file():
        return _DEFAULT_WIN_PATH

    for name in _BINARY_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)

    return None


class TetGenEngine(MeshingEngineBase):
    """
    TetGen volume-mesh adapter (subprocess binary).

    Converts a closed triangulated surface into a quality-constrained
    tetrahedral volume mesh by invoking the ``tetgen`` executable.

    Accepted geometry types:

    - ``SurfaceMeshGeometry`` — vertices + triangles arrays written to a
      temporary ``.smesh`` file.
    - ``FileGeometry``        — STL file path passed directly via ``-p``.

    The binary is located via :func:`_find_tetgen_exe`.
    """

    name         = "tetgen"
    display_name = "TetGen"
    priority     = 50
    license_type = LicenseType.DUAL
    capabilities = EngineCapabilities(
        volume_mesh=True,
        mesh_refinement=True,
        formats_in=["stl", "smesh", "node"],
        formats_out=["node", "ele"],
    )

    @classmethod
    def is_available(cls) -> bool:
        return _find_tetgen_exe() is not None

    @classmethod
    def get_version(cls) -> Optional[str]:
        exe = _find_tetgen_exe()
        if exe is None:
            return None
        try:
            proc = subprocess.run(
                [str(exe)],
                capture_output=True, text=True, timeout=10,
            )
            output = (proc.stdout + proc.stderr).strip()
            for line in output.splitlines():
                line = line.strip()
                if line:
                    return line[:120]
            return "unknown"
        except Exception:
            return None

    # ── Volume mesh ───────────────────────────────────────────────────────────

    def generate_volume_mesh(self, request: VolumeMeshRequest) -> MeshResult:
        exe = _find_tetgen_exe()
        if exe is None:
            return MeshResult.failure(
                self.name,
                "TetGen binary not found. Set TETGEN_EXE or place tetgen.exe "
                "in C:\\bin\\ or on PATH.",
            )

        t0 = time.monotonic()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            geom = request.geometry

            if isinstance(geom, SurfaceMeshGeometry):
                input_file = tmp_path / "input.smesh"
                _write_smesh(input_file, geom.vertices, geom.triangles)
                stem = "input"
            elif isinstance(geom, FileGeometry):
                input_file = Path(geom.path)
                stem = input_file.stem
            else:
                return MeshResult.failure(
                    self.name,
                    "TetGenEngine requires SurfaceMeshGeometry or FileGeometry (STL).",
                )

            # Quality ratio derived from request (higher quality → lower ratio)
            min_ratio = 1.0 + max(0.0, 1.0 - request.min_quality) * 2.0
            cmd = [str(exe), f"-pq{min_ratio:.3f}", str(input_file)]
            logger.debug("TetGenEngine: %s", " ".join(cmd))

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True, text=True,
                    cwd=str(tmp_path), timeout=300,
                )
            except subprocess.TimeoutExpired:
                return MeshResult.failure(self.name, "tetgen timed out (>300 s)")
            except Exception as exc:
                return MeshResult.failure(self.name, f"tetgen execution error: {exc}")

            if proc.returncode != 0:
                return MeshResult.failure(
                    self.name,
                    f"tetgen exited {proc.returncode}: {(proc.stderr or proc.stdout)[:500]}",
                )

            node_file = tmp_path / f"{stem}.1.node"
            ele_file  = tmp_path / f"{stem}.1.ele"

            if not node_file.exists() or not ele_file.exists():
                return MeshResult.failure(
                    self.name,
                    f"Expected output files not found ({stem}.1.node / {stem}.1.ele). "
                    f"stderr: {proc.stderr[:300]}",
                )

            try:
                vertices = _read_node_file(node_file)
                elements = _read_ele_file(ele_file)
            except Exception as exc:
                return MeshResult.failure(self.name, f"Failed to parse tetgen output: {exc}")

        elapsed = time.monotonic() - t0
        mesh_data = MeshData(
            vertices=vertices,
            elements=elements,
            element_type=ElementType.TET4,
            engine_name=self.name,
            generation_time_s=elapsed,
        )
        return MeshResult(
            success=True,
            engine_used=self.name,
            fds_meshes=[],
            mesh_data=mesh_data,
            elapsed_s=elapsed,
            stats={"n_vertices": len(vertices), "n_elements": len(elements)},
        )


# ---------------------------------------------------------------------------
# TetGen file I/O helpers
# ---------------------------------------------------------------------------

def _write_smesh(path: Path, vertices: np.ndarray, triangles: np.ndarray) -> None:
    """Write a TetGen .smesh surface-mesh file (1-based node indices)."""
    lines: list[str] = []

    # Part 1 — node list
    lines.append(f"{len(vertices)} 3 0 0")
    for i, (x, y, z) in enumerate(vertices, start=1):
        lines.append(f"{i}  {x:.10g}  {y:.10g}  {z:.10g}")
    lines.append("")

    # Part 2 — facet list (triangles, 1-based)
    lines.append(f"{len(triangles)} 0")
    for tri in triangles:
        a, b, c = int(tri[0]) + 1, int(tri[1]) + 1, int(tri[2]) + 1
        lines.append(f"3  {a}  {b}  {c}")
    lines.append("")

    # Part 3 — hole list (empty)
    lines.append("0")
    lines.append("")

    # Part 4 — region list (empty)
    lines.append("0")

    path.write_text("\n".join(lines))


def _read_node_file(path: Path) -> np.ndarray:
    """Parse a TetGen .node file → (N, 3) float64."""
    raw = [l.strip() for l in path.read_text().splitlines()
           if l.strip() and not l.strip().startswith("#")]
    n = int(raw[0].split()[0])
    verts = []
    for line in raw[1:n + 1]:
        p = line.split()
        verts.append([float(p[1]), float(p[2]), float(p[3])])
    return np.array(verts, dtype=np.float64)


def _read_ele_file(path: Path) -> np.ndarray:
    """Parse a TetGen .ele file → (M, 4) int32, 0-based indices."""
    raw = [l.strip() for l in path.read_text().splitlines()
           if l.strip() and not l.strip().startswith("#")]
    n = int(raw[0].split()[0])
    tets = []
    for line in raw[1:n + 1]:
        p = line.split()
        tets.append([int(p[1]) - 1, int(p[2]) - 1, int(p[3]) - 1, int(p[4]) - 1])
    return np.array(tets, dtype=np.int32)
