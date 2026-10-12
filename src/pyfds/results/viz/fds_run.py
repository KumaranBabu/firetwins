"""The ``.smv`` file of an FDS run as a typed model (the thing the results viewer opens).

Written against real FDS 6.10.1 output (see ``tests/fixtures/results_room``). The older
``results.smv_parser`` stays for the Smokeview-INI tools; this one keeps what the viewer needs: true mesh
node coordinates (so stretched meshes are right), the geometry FDS actually used, every output file with its
mesh / quantity / slice plane, particle classes and the run's colour ranges.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

_KEYWORDS = {
    "TITLE", "FDSVERSION", "INPF", "REVISION", "CHID", "CSVF", "NMESHES", "TIMES", "VIEWTIMES", "ALBEDO",
    "CLASS_OF_PARTICLES", "TOFFSET", "HRRPUVCUT", "HRRPUV_MINMAX", "TEMP_MINMAX", "PROP", "OFFSET", "GRID", "PDIM",
    "TRNX", "TRNY", "TRNZ", "OBST", "VENT", "CVENT", "VENTORIG", "OUTLINE", "ISOG", "ISOF", "TISOF", "SMOKF3D",
    "SMOKG3D", "SLCF", "SLCC", "SLCT", "BNDF", "BNDC", "PRT5", "PL3D", "DEVICE", "DEVICE_ACT", "SURFACE", "SURFDEF",
    "GVEC", "IBLANK", "HoC", "FUEL", "AMBIENT", "SMOKEDIFF", "TREE", "GEOM", "GEOMDIAG", "SHOW_OBST", "HIDE_OBST",
    "OPEN_VENT", "CLOSE_VENT", "VIEW", "DEVICE_ACT",
}
_KW_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\b")


@dataclass
class Mesh:
    index: int                                  # 1-based, the number used in file names
    name: str = ""
    ijk: Tuple[int, int, int] = (0, 0, 0)
    extents: Tuple[float, float, float, float, float, float] = (0, 0, 0, 0, 0, 0)
    nodes: Tuple[np.ndarray, np.ndarray, np.ndarray] = field(default_factory=lambda: (np.zeros(0),) * 3)

    def node_coords(self, axis: int) -> np.ndarray:
        """Cell-boundary coordinates along *axis*; the real (possibly stretched) ones when the file lists them."""
        n = self.nodes[axis]
        if len(n) == self.ijk[axis] + 1:
            return n
        return np.linspace(self.extents[2 * axis], self.extents[2 * axis + 1], self.ijk[axis] + 1)

    @property
    def uniform(self) -> bool:
        return all(np.allclose(np.diff(self.node_coords(a)), np.diff(self.node_coords(a))[0]) for a in range(3))


@dataclass
class Obst:
    name: str
    xb: Tuple[float, float, float, float, float, float]
    mesh: int = 1


@dataclass
class Vent:
    xb: Tuple[float, float, float, float, float, float]
    index: int = 0
    mesh: int = 1


@dataclass
class SliceFile:
    file: str
    mesh: int
    quantity: str
    short: str
    units: str
    name: str                                   # the FDS ID given in the input (``%`` token)
    ijk: Tuple[int, int, int, int, int, int]    # i1 i2 j1 j2 k1 k2 (node indices)
    slice_id: int = 0                           # same id = same slice in different quantities (vectors)
    idir: int = 0                               # 1/2/3 = plane normal to x/y/z, 0 = volume
    cell_centered: bool = False

    @property
    def is_volume(self) -> bool:
        return self.idir == 0

    @property
    def plane_label(self) -> str:
        return "XYZ"[self.idir - 1] if self.idir else "3D"


@dataclass
class OutputFile:
    file: str
    mesh: int
    quantity: str
    short: str = ""
    units: str = ""
    extra: float = 0.0


@dataclass
class ParticleClass:
    name: str
    color: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    quantities: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class Plot3DFile:
    file: str
    mesh: int
    time: float
    quantities: List[Tuple[str, str, str]]      # (quantity, short, units) x 5


@dataclass
class Device:
    name: str
    quantity: str = ""
    xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class FdsRun:
    path: str
    chid: str = ""
    title: str = ""
    fds_version: str = ""
    input_file: str = ""
    times: Tuple[float, float] = (0.0, 0.0)
    hrrpuv_range: Tuple[float, float] = (0.0, 1200.0)
    temp_range: Tuple[float, float] = (20.0, 2000.0)
    hrrpuv_cutoff: float = 200.0
    meshes: List[Mesh] = field(default_factory=list)
    obstructions: List[Obst] = field(default_factory=list)
    vents: List[Vent] = field(default_factory=list)
    slices: List[SliceFile] = field(default_factory=list)
    boundaries: List[OutputFile] = field(default_factory=list)
    isosurfaces: List[OutputFile] = field(default_factory=list)
    smoke3d: List[OutputFile] = field(default_factory=list)
    particles: List[OutputFile] = field(default_factory=list)
    particle_classes: List[ParticleClass] = field(default_factory=list)
    plot3d: List[Plot3DFile] = field(default_factory=list)
    devices: List[Device] = field(default_factory=list)
    csv_files: List[str] = field(default_factory=list)

    # -- helpers -------------------------------------------------------------------------
    @property
    def directory(self) -> Path:
        return Path(self.path).resolve().parent

    def resolve(self, name: str) -> Path:
        return self.directory / name

    def mesh(self, index: int) -> Mesh:
        for m in self.meshes:
            if m.index == index:
                return m
        raise KeyError(f"mesh {index} not in {self.path}")

    def bounds(self) -> Tuple[float, ...]:
        if not self.meshes:
            return (0.0,) * 6
        e = np.array([m.extents for m in self.meshes])
        return (e[:, 0].min(), e[:, 1].max(), e[:, 2].min(), e[:, 3].max(), e[:, 4].min(), e[:, 5].max())

    def slice_coords(self, s: SliceFile) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Coordinates of the nodes a slice covers along x, y, z (cell centres when ``cell_centered``)."""
        m = self.mesh(s.mesh)
        out = []
        for a in range(3):
            nodes = m.node_coords(a)
            lo, hi = s.ijk[2 * a], s.ijk[2 * a + 1]
            idx = np.clip(np.arange(lo, hi + 1), 0, len(nodes) - 1)
            c = nodes[idx]
            if s.cell_centered and hi > lo:
                c = 0.5 * (nodes[np.clip(np.arange(lo, hi), 0, len(nodes) - 1)] +
                           nodes[np.clip(np.arange(lo + 1, hi + 1), 0, len(nodes) - 1)])
            out.append(c)
        return out[0], out[1], out[2]

    def vector_groups(self) -> Dict[Tuple[int, int], Dict[str, SliceFile]]:
        """``{(mesh, slice_id): {"U": .., "V": .., "W": ..}}`` for slices FDS wrote with VECTOR=T."""
        found: Dict[Tuple[int, int], Dict[str, SliceFile]] = {}
        for s in self.slices:
            tag = {"U-VELOCITY": "U", "V-VELOCITY": "V", "W-VELOCITY": "W"}.get(s.quantity.upper())
            if tag:
                found.setdefault((s.mesh, s.slice_id), {})[tag] = s
        return {k: v for k, v in found.items() if set(v) == {"U", "V", "W"}}

    def summary(self) -> str:
        return (f"{self.chid}: {len(self.meshes)} mesh(es), {len(self.slices)} slice files, "
                f"{len(self.boundaries)} boundary, {len(self.isosurfaces)} iso, {len(self.smoke3d)} smoke3d, "
                f"{len(self.particles)} particle, {len(self.plot3d)} plot3d, t = {self.times[0]:g}..{self.times[1]:g} s")


# -- parsing ---------------------------------------------------------------------------------------
def _blocks(lines: Sequence[str]):
    """Yield (keyword, header_args, data_lines). A keyword line starts in column 0 with a known keyword."""
    key, args, data = None, "", []
    for raw in lines:
        line = raw.rstrip("\r\n")
        m = _KW_RE.match(line) if line and not line[0].isspace() else None
        if m and m.group(1) in _KEYWORDS:
            if key is not None:
                yield key, args, data
            key, args, data = m.group(1), line[m.end():].strip(), []
        elif key is not None:
            data.append(line)
    if key is not None:
        yield key, args, data


def _floats(line: str) -> List[float]:
    out = []
    for tok in line.replace(",", " ").split():
        try:
            out.append(float(tok))
        except ValueError:
            break
    return out


def _txt(data: Sequence[str], i: int) -> str:
    return data[i].strip() if i < len(data) else ""


def parse_smv(path: str) -> FdsRun:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"SMV file not found: {path}")
    run = FdsRun(path=str(p))
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    mesh: Optional[Mesh] = None
    trn_target: Optional[str] = None
    for key, args, data in _blocks(lines):
        d = [x for x in data if x.strip()]
        if key == "TITLE":
            run.title = _txt(d, 0)
        elif key == "FDSVERSION":
            run.fds_version = _txt(d, 0)
        elif key == "INPF":
            run.input_file = _txt(d, 0)
        elif key == "CHID":
            run.chid = _txt(d, 0)
        elif key == "CSVF":
            if len(d) >= 2:
                run.csv_files.append(d[1].strip())
        elif key == "TIMES":
            v = _floats(d[0]) if d else []
            if len(v) >= 2:
                run.times = (v[0], v[1])
        elif key == "HRRPUV_MINMAX":
            v = _floats(d[0]) if d else []
            if len(v) >= 2:
                run.hrrpuv_range = (v[0], v[1])
        elif key == "TEMP_MINMAX":
            v = _floats(d[0]) if d else []
            if len(v) >= 2:
                run.temp_range = (v[0], v[1])
        elif key == "HRRPUVCUT":
            v = _floats(d[0]) if d else []
            if v:
                run.hrrpuv_cutoff = float(v[0])
        elif key == "CLASS_OF_PARTICLES":
            rgb = tuple(_floats(d[1])[:3]) if len(d) > 1 else (0.0, 0.0, 1.0)
            nq = int(_floats(d[2])[0]) if len(d) > 2 and _floats(d[2]) else 0
            quantities = [(d[3 + 2 * i].strip(), d[4 + 2 * i].strip()) for i in range(nq) if 4 + 2 * i < len(d)]
            run.particle_classes.append(ParticleClass(_txt(d, 0), rgb if len(rgb) == 3 else (0, 0, 1), quantities))
        elif key == "GRID":
            v = [int(float(x)) for x in d[0].split()[:3]] if d else [0, 0, 0]
            mesh = Mesh(index=len(run.meshes) + 1, name=args.strip(), ijk=(v[0], v[1], v[2]))
            run.meshes.append(mesh)
        elif key == "PDIM" and mesh is not None:
            v = _floats(d[0]) if d else []
            if len(v) >= 6:
                mesh.extents = tuple(v[:6])
        elif key in ("TRNX", "TRNY", "TRNZ") and mesh is not None:
            axis = "XYZ".index(key[3])
            coords = []
            for ln in d[1:]:
                f = _floats(ln)
                if len(f) >= 2:
                    coords.append(f[1])
            nodes = list(mesh.nodes)
            nodes[axis] = np.array(coords, dtype=float)
            mesh.nodes = tuple(nodes)                   # type: ignore[assignment]
        elif key == "OBST" and mesh is not None:
            n = int(float(d[0])) if d else 0
            for ln in d[1:1 + n]:
                head, _, name = ln.partition("!")
                f = _floats(head)
                if len(f) >= 6:
                    run.obstructions.append(Obst(name.strip(), tuple(f[:6]), mesh.index))      # type: ignore[arg-type]
        elif key == "VENT" and mesh is not None:
            n = int(float(d[0].split()[0])) if d else 0
            for ln in d[1:1 + n]:
                f = _floats(ln)
                if len(f) >= 7:
                    run.vents.append(Vent(tuple(f[:6]), int(f[6]), mesh.index))               # type: ignore[arg-type]
        elif key in ("SLCF", "SLCC"):
            s = _parse_slice(key, args, d)
            if s is not None:
                run.slices.append(s)
        elif key in ("BNDF", "BNDC"):
            run.boundaries.append(_output(args, d))
        elif key in ("ISOG", "ISOF"):
            run.isosurfaces.append(_output(args, d))
        elif key in ("SMOKF3D", "SMOKG3D"):
            o = _output(args, d)
            toks = args.split()
            o.extra = float(toks[1]) if len(toks) > 1 else 0.0
            run.smoke3d.append(o)
        elif key == "PRT5":
            run.particles.append(OutputFile(_txt(d, 0), int(args.split()[0]) if args.split() else 1, "PARTICLES"))
        elif key == "PL3D":
            toks = args.split()
            q = [(_txt(d, 1 + 3 * i), _txt(d, 2 + 3 * i), _txt(d, 3 + 3 * i)) for i in range(5)]
            run.plot3d.append(Plot3DFile(_txt(d, 0), int(toks[1]) if len(toks) > 1 else 1, float(toks[0]) if toks else 0.0, q))
        elif key == "DEVICE" and len(d) >= 2:
            name, _, qty = d[0].partition("%")
            xyz = _floats(d[1])[:3]
            run.devices.append(Device(name.strip(), qty.strip(), tuple(xyz) if len(xyz) == 3 else (0, 0, 0)))   # type: ignore
    if not run.chid:
        run.chid = p.stem
    return run


def _output(args: str, d: Sequence[str]) -> OutputFile:
    toks = args.split()
    return OutputFile(_txt(d, 0), int(float(toks[0])) if toks else 1, _txt(d, 1), _txt(d, 2), _txt(d, 3))


def _parse_slice(key: str, args: str, d: Sequence[str]) -> Optional[SliceFile]:
    toks = args.replace("&", " & ").replace("!", " ! ").replace("%", " % ").split()
    if not toks:
        return None
    try:
        mesh = int(float(toks[0]))
        name = toks[toks.index("%") + 1] if "%" in toks and toks.index("%") + 1 < len(toks) else ""
        amp = toks.index("&")
        ijk = tuple(int(float(t)) for t in toks[amp + 1:amp + 7])
        bang = toks.index("!") if "!" in toks else -1
        tail = [int(float(t)) for t in toks[bang + 1:bang + 4]] if bang >= 0 else []
    except (ValueError, IndexError):
        return None
    if len(ijk) != 6:
        return None
    return SliceFile(file=_txt(d, 0), mesh=mesh, quantity=_txt(d, 1), short=_txt(d, 2), units=_txt(d, 3), name=name,
                     ijk=ijk, slice_id=tail[0] if tail else 0, idir=tail[2] if len(tail) > 2 else 0,    # type: ignore
                     cell_centered=(key == "SLCC"))
