"""
PyFDS Result Indexer
====================
Indexes all FDS output files in a case directory so callers can search by
time range, mesh, quantity, or file type without scanning the file system
repeatedly.

Classes
-------
SliceIndex      — metadata index over ``*.sf`` slice files
BoundaryIndex   — metadata index over ``*.bf`` boundary files
ResultIndex     — top-level aggregate: devices, log, slices, boundaries

Usage::

    idx = ResultIndex.build(output_dir="batch_results/case_01",
                            chid="hrr_case")
    # List all slice quantities available
    print(idx.slice_quantities())

    # Find slice files for a specific quantity
    for entry in idx.find_slices(quantity="TEMPERATURE"):
        header, frames = SliceReader().read(entry.filepath)
        ...

    # Check if the simulation completed
    print(idx.stats.completed, idx.stats.t_reached)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .reader import (
    DeviceReader,
    LogParser,
    SimulationStats,
    SliceReader,
    SliceHeader,
    BoundaryReader,
    BoundaryHeader,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slice index
# ---------------------------------------------------------------------------

@dataclass
class SliceIndexEntry:
    """Lightweight metadata record for one ``*.sf`` file."""
    filepath: str
    quantity: str
    short_name: str
    units: str
    mesh_id: Optional[int]    # extracted from filename pattern e.g. ``_01.sf``
    i1: int; i2: int
    j1: int; j2: int
    k1: int; k2: int

    @property
    def is_2d(self) -> bool:
        return (self.i1 == self.i2 or
                self.j1 == self.j2 or
                self.k1 == self.k2)


# Pattern: <anything>_<NN>.sf  where NN is the mesh number
_SF_MESH_RE  = re.compile(r'_(\d+)\.sf$', re.IGNORECASE)
_BF_MESH_RE  = re.compile(r'_(\d+)\.bf$', re.IGNORECASE)


class SliceIndex:
    """
    Scans a directory for ``*.sf`` files and builds a lightweight index
    without reading all frame data.

    The index reads only the 4-record header of each file (< 200 bytes)
    so building it is fast even for hundreds of files.
    """

    def __init__(self) -> None:
        self._entries: List[SliceIndexEntry] = []

    @classmethod
    def build(cls, output_dir: str) -> "SliceIndex":
        idx = cls()
        idx._scan(output_dir)
        return idx

    def _scan(self, output_dir: str) -> None:
        self._entries.clear()
        dir_path = Path(output_dir)
        self._scan_files(sorted(dir_path.glob("*.sf")))

    def _scan_files(self, sf_files) -> None:
        for sf in sf_files:
            sf = Path(sf)
            try:
                header, frames = SliceReader._read_raw(str(sf))
                m = _SF_MESH_RE.search(sf.name)
                mesh_id = int(m.group(1)) if m else None
                self._entries.append(SliceIndexEntry(
                    filepath=str(sf),
                    quantity=header.quantity,
                    short_name=header.short_name,
                    units=header.units,
                    mesh_id=mesh_id,
                    i1=header.i1, i2=header.i2,
                    j1=header.j1, j2=header.j2,
                    k1=header.k1, k2=header.k2,
                ))
                logger.debug("SliceIndex: indexed %s (%s)", sf.name, header.quantity)
            except Exception as exc:
                logger.warning("SliceIndex: skipping %s: %s", sf.name, exc)

    # ── Query ─────────────────────────────────────────────────────────────────

    def all_entries(self) -> List[SliceIndexEntry]:
        return list(self._entries)

    def quantities(self) -> List[str]:
        """Unique quantity names across all indexed slice files."""
        seen = {}
        for e in self._entries:
            seen[e.quantity] = True
        return list(seen.keys())

    def find(
        self,
        *,
        quantity: Optional[str] = None,
        mesh_id: Optional[int] = None,
        planar_only: bool = False,
    ) -> List[SliceIndexEntry]:
        """
        Filter entries.

        Parameters
        ----------
        quantity : str, optional
            Case-insensitive substring match on the quantity name.
        mesh_id : int, optional
            Return only entries from this mesh number.
        planar_only : bool
            If True, return only 2-D (single-cell-thick) slices.
        """
        results = self._entries
        if quantity:
            q_lower = quantity.lower()
            results = [e for e in results if q_lower in e.quantity.lower()]
        if mesh_id is not None:
            results = [e for e in results if e.mesh_id == mesh_id]
        if planar_only:
            results = [e for e in results if e.is_2d]
        return results

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"<SliceIndex entries={len(self._entries)} quantities={self.quantities()}>"


# ---------------------------------------------------------------------------
# Boundary index
# ---------------------------------------------------------------------------

@dataclass
class BoundaryIndexEntry:
    """Lightweight metadata record for one ``*.bf`` file."""
    filepath: str
    quantity: str
    short_name: str
    units: str
    mesh_id: Optional[int]
    n_patches: int


class BoundaryIndex:
    """
    Scans a directory for ``*.bf`` files and builds a lightweight metadata
    index (headers only, no frame data loaded).
    """

    def __init__(self) -> None:
        self._entries: List[BoundaryIndexEntry] = []

    @classmethod
    def build(cls, output_dir: str) -> "BoundaryIndex":
        idx = cls()
        idx._scan(output_dir)
        return idx

    def _scan(self, output_dir: str) -> None:
        self._entries.clear()
        dir_path = Path(output_dir)
        self._scan_files(sorted(dir_path.glob("*.bf")))

    def _scan_files(self, bf_files) -> None:
        reader = BoundaryReader()
        for bf in bf_files:
            bf = Path(bf)
            try:
                header, patches, _ = reader.read(str(bf))
                m = _BF_MESH_RE.search(bf.name)
                mesh_id = int(m.group(1)) if m else None
                self._entries.append(BoundaryIndexEntry(
                    filepath=str(bf),
                    quantity=header.quantity,
                    short_name=header.short_name,
                    units=header.units,
                    mesh_id=mesh_id,
                    n_patches=header.n_patches,
                ))
                logger.debug("BoundaryIndex: indexed %s (%s)", bf.name, header.quantity)
            except Exception as exc:
                logger.warning("BoundaryIndex: skipping %s: %s", bf.name, exc)

    def all_entries(self) -> List[BoundaryIndexEntry]:
        return list(self._entries)

    def quantities(self) -> List[str]:
        seen: Dict[str, bool] = {}
        for e in self._entries:
            seen[e.quantity] = True
        return list(seen.keys())

    def find(
        self,
        *,
        quantity: Optional[str] = None,
        mesh_id: Optional[int] = None,
    ) -> List[BoundaryIndexEntry]:
        results = self._entries
        if quantity:
            q_lower = quantity.lower()
            results = [e for e in results if q_lower in e.quantity.lower()]
        if mesh_id is not None:
            results = [e for e in results if e.mesh_id == mesh_id]
        return results

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"<BoundaryIndex entries={len(self._entries)} quantities={self.quantities()}>"


# ---------------------------------------------------------------------------
# ResultIndex — top-level aggregate
# ---------------------------------------------------------------------------

@dataclass
class DeviceFile:
    filepath: str
    chid: str
    device_names: List[str] = field(default_factory=list)


class ResultIndex:
    """
    Aggregate index for an entire FDS case output directory.

    Discovers and indexes:
    - ``*.smv``          → SMV metadata (mesh geometry, output file list, device locations)
    - ``*.out``          → simulation stats via ``LogParser``
    - ``*_devc.csv``     → device CSV headers via ``DeviceReader``
    - ``*.sf``           → slice files via ``SliceIndex``
    - ``*.bf``           → boundary files via ``BoundaryIndex``
    - ``*.q``            → Plot3D binary files (paths only)
    - ``*.prt5``         → particle binary files (paths only)

    When a ``.smv`` file is present, :meth:`build` uses it as the authoritative
    source of output-file metadata (quantity names, units, mesh IDs, IJK extents)
    instead of reading each binary header individually.  This is faster and
    exposes additional data (device XYZ locations, mesh extents) not available
    from directory scanning alone.

    Example::

        idx = ResultIndex.build("output/case_01", chid="case_01")
        print(idx.stats.completed)
        print(idx.slice_quantities())
        sf_entries = idx.find_slices(quantity="TEMP")
        q_files    = idx.find_plot3d()
        prt_files  = idx.find_particles()

        # SMV-derived device locations (xyz positions)
        for name, dev in idx.smv_devices.items():
            print(name, dev.x, dev.y, dev.z)
    """

    def __init__(self) -> None:
        self.output_dir: str = ""
        self.chid: str = ""
        self.stats: SimulationStats = SimulationStats()
        self.device_files: List[DeviceFile] = []
        self.slice_index: SliceIndex = SliceIndex()
        self.boundary_index: BoundaryIndex = BoundaryIndex()
        self.plot3d_files: List[str] = []
        self.particle_files: List[str] = []
        # SMV-derived data (populated when a .smv file is found)
        self.smv_metadata: Optional[Any] = None         # SmvMetadata instance
        self.smv_devices: Dict[str, Any] = {}           # device_name → SmvDevice
        self.smv_grids: List[Any] = []                  # SmvGrid list (mesh extents)
        self.smv_filepath: Optional[str] = None

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        output_dir: str,
        chid: Optional[str] = None,
        *,
        index_slices: bool = True,
        index_boundaries: bool = True,
        index_plot3d: bool = True,
        index_particles: bool = True,
        use_smv: bool = True,
    ) -> "ResultIndex":
        """
        Build a full index for *output_dir*.

        When *use_smv* is True (default) and a ``.smv`` file is found in
        *output_dir*, the SMV file is used as the primary source of output-file
        metadata instead of reading each binary header individually.  Binary
        header reads are still performed for any files not listed in the SMV.

        Parameters
        ----------
        output_dir : str
            Directory containing FDS output files.
        chid : str, optional
            Case ID; if omitted, inferred from the ``.smv`` or ``.out`` file.
        index_slices : bool
            Whether to scan and index ``*.sf`` files.
        index_boundaries : bool
            Whether to scan and index ``*.bf`` files.
        index_plot3d : bool
            Whether to scan and record ``*.q`` Plot3D file paths.
        index_particles : bool
            Whether to scan and record ``*.prt5`` particle file paths.
        use_smv : bool
            Use the ``.smv`` file as the primary metadata source when present.
        """
        idx = cls()
        idx.output_dir = str(output_dir)
        dir_path = Path(output_dir)

        # ── Try SMV-first path ────────────────────────────────────────────────
        smv_files = sorted(dir_path.glob("*.smv"))
        smv_path = smv_files[0] if smv_files else None

        if use_smv and smv_path:
            try:
                idx._ingest_smv(smv_path, dir_path)
                if chid:
                    idx.chid = chid
                elif idx.chid:
                    pass  # from SMV
                logger.info("ResultIndex: SMV-enhanced build from %s", smv_path.name)
            except Exception as exc:
                logger.warning("ResultIndex: SMV parse failed (%s), falling back", exc)
                smv_path = None  # fall through to directory scan

        # ── Infer CHID from .out / directory name if still unknown ───────────
        if not idx.chid:
            if chid:
                idx.chid = chid
            else:
                out_files = list(dir_path.glob("*.out"))
                idx.chid = out_files[0].stem if out_files else dir_path.name

        logger.info("ResultIndex.build: scanning %s (chid=%s)", output_dir, idx.chid)

        # ── Parse .out log ────────────────────────────────────────────────────
        out_path = dir_path / f"{idx.chid}.out"
        if out_path.exists():
            idx.stats = LogParser().parse(str(out_path))
        else:
            for p in dir_path.glob("*.out"):
                try:
                    idx.stats = LogParser().parse(str(p))
                except Exception:
                    pass
                break

        # ── Index device CSVs ─────────────────────────────────────────────────
        devc_reader = DeviceReader()
        for csv_path in sorted(dir_path.glob("*_devc.csv")):
            try:
                results = devc_reader.read(str(csv_path))
                names = [k for k in results.keys() if k.lower() != "time"]
                case_chid = csv_path.stem.replace("_devc", "")
                idx.device_files.append(DeviceFile(
                    filepath=str(csv_path),
                    chid=case_chid,
                    device_names=names,
                ))
                logger.debug("ResultIndex: %d devices from %s", len(names), csv_path.name)
            except Exception as exc:
                logger.warning("ResultIndex: skipping device CSV %s: %s", csv_path.name, exc)

        # ── Slice / boundary / Plot3D / particle indexing ─────────────────────
        # When the SMV already populated these, skip binary re-scan for known
        # files; still pick up any additional files not in the SMV listing.
        smv_sf_paths  = {e.filepath for e in idx.slice_index.all_entries()}
        smv_bf_paths  = {e.filepath for e in idx.boundary_index.all_entries()}
        smv_q_paths   = set(idx.plot3d_files)
        smv_prt_paths = set(idx.particle_files)

        if index_slices:
            extra_sf = [
                f for f in sorted(dir_path.glob("*.sf"))
                if str(f) not in smv_sf_paths
            ]
            if extra_sf:
                extra_idx = SliceIndex()
                extra_idx._scan_files(extra_sf)
                idx.slice_index._entries.extend(extra_idx._entries)
            if not smv_sf_paths:
                idx.slice_index = SliceIndex.build(output_dir)

        if index_boundaries:
            extra_bf = [
                f for f in sorted(dir_path.glob("*.bf"))
                if str(f) not in smv_bf_paths
            ]
            if extra_bf:
                extra_bidx = BoundaryIndex()
                extra_bidx._scan_files(extra_bf)
                idx.boundary_index._entries.extend(extra_bidx._entries)
            if not smv_bf_paths:
                idx.boundary_index = BoundaryIndex.build(output_dir)

        if index_plot3d:
            for q_path in sorted(dir_path.glob("*.q")):
                if str(q_path) not in smv_q_paths:
                    idx.plot3d_files.append(str(q_path))
                    logger.debug("ResultIndex: found extra Plot3D %s", q_path.name)

        if index_particles:
            for prt_path in sorted(dir_path.glob("*.prt5")):
                if str(prt_path) not in smv_prt_paths:
                    idx.particle_files.append(str(prt_path))
                    logger.debug("ResultIndex: found extra particle %s", prt_path.name)

        logger.info(
            "ResultIndex built: slices=%d  boundaries=%d  devc_files=%d  "
            "plot3d=%d  particles=%d  completed=%s  smv=%s",
            len(idx.slice_index), len(idx.boundary_index),
            len(idx.device_files), len(idx.plot3d_files),
            len(idx.particle_files), idx.stats.completed,
            bool(idx.smv_filepath),
        )
        return idx

    @classmethod
    def build_from_smv(cls, smv_filepath: str) -> "ResultIndex":
        """
        Build an index directly from a ``.smv`` file.

        The output directory is inferred from the SMV file's parent directory.
        This is the fastest build path when a ``.smv`` file is available: no
        binary header reads are performed.

        Parameters
        ----------
        smv_filepath : str
            Absolute or relative path to the ``.smv`` file.
        """
        smv_path = Path(smv_filepath)
        idx = cls()
        idx.output_dir = str(smv_path.parent)
        idx._ingest_smv(smv_path, smv_path.parent)

        # Parse .out log
        out_path = smv_path.parent / f"{idx.chid}.out"
        if out_path.exists():
            idx.stats = LogParser().parse(str(out_path))
        else:
            for p in smv_path.parent.glob("*.out"):
                try:
                    idx.stats = LogParser().parse(str(p))
                except Exception:
                    pass
                break

        # Index device CSVs
        devc_reader = DeviceReader()
        for csv_path in sorted(smv_path.parent.glob("*_devc.csv")):
            try:
                results = devc_reader.read(str(csv_path))
                names = [k for k in results.keys() if k.lower() != "time"]
                idx.device_files.append(DeviceFile(
                    filepath=str(csv_path),
                    chid=csv_path.stem.replace("_devc", ""),
                    device_names=names,
                ))
            except Exception as exc:
                logger.warning("ResultIndex: skipping %s: %s", csv_path.name, exc)

        logger.info("ResultIndex.build_from_smv: %s  grids=%d  slices=%d",
                    smv_path.name, len(idx.smv_grids), len(idx.slice_index))
        return idx

    def _ingest_smv(self, smv_path: Path, base_dir: Path) -> None:
        """Populate index fields from a parsed SMV file."""
        from pyfds.results.smv_parser import SmvParser
        meta = SmvParser().parse(str(smv_path))
        self.smv_metadata = meta
        self.smv_filepath = str(smv_path)
        self.chid = meta.chid or smv_path.stem
        self.smv_grids = list(meta.grids)

        # Device locations
        for dev in meta.devices:
            self.smv_devices[dev.name] = dev

        # Slice entries from SMV (no binary header read)
        for slc in meta.slices:
            fp = str(base_dir / slc.filepath) if not Path(slc.filepath).is_absolute() else slc.filepath
            self.slice_index._entries.append(SliceIndexEntry(
                filepath=fp,
                quantity=slc.quantity,
                short_name=slc.short_name,
                units=slc.units,
                mesh_id=slc.mesh_id,
                i1=slc.i1, i2=slc.i2,
                j1=slc.j1, j2=slc.j2,
                k1=slc.k1, k2=slc.k2,
            ))

        # Boundary entries from SMV
        for bndf in meta.boundaries:
            fp = str(base_dir / bndf.filepath) if not Path(bndf.filepath).is_absolute() else bndf.filepath
            self.boundary_index._entries.append(BoundaryIndexEntry(
                filepath=fp,
                quantity=bndf.quantity,
                short_name=bndf.short_name,
                units=bndf.units,
                mesh_id=bndf.mesh_id,
                n_patches=0,   # SMV doesn't give patch count; read lazily
            ))

        # Plot3D paths from SMV
        for pl in meta.plot3d:
            fp = str(base_dir / pl.filepath) if not Path(pl.filepath).is_absolute() else pl.filepath
            self.plot3d_files.append(fp)

        # Particle paths from SMV
        for prt in meta.particles:
            fp = str(base_dir / prt.filepath) if not Path(prt.filepath).is_absolute() else prt.filepath
            self.particle_files.append(fp)

    # ── Query helpers ──────────────────────────────────────────────────────────

    def slice_quantities(self) -> List[str]:
        """Unique quantity names across all indexed ``*.sf`` files."""
        return self.slice_index.quantities()

    def boundary_quantities(self) -> List[str]:
        """Unique quantity names across all indexed ``*.bf`` files."""
        return self.boundary_index.quantities()

    def all_device_names(self) -> List[str]:
        """Flat list of all device names across all device CSV files."""
        names: List[str] = []
        for df in self.device_files:
            names.extend(df.device_names)
        return names

    def find_slices(
        self,
        *,
        quantity: Optional[str] = None,
        mesh_id: Optional[int] = None,
        planar_only: bool = False,
    ) -> List[SliceIndexEntry]:
        return self.slice_index.find(
            quantity=quantity, mesh_id=mesh_id, planar_only=planar_only,
        )

    def find_boundaries(
        self,
        *,
        quantity: Optional[str] = None,
        mesh_id: Optional[int] = None,
    ) -> List[BoundaryIndexEntry]:
        return self.boundary_index.find(quantity=quantity, mesh_id=mesh_id)

    def find_plot3d(self) -> List[str]:
        """Return all indexed ``*.q`` Plot3D file paths."""
        return list(self.plot3d_files)

    def find_particles(self) -> List[str]:
        """Return all indexed ``*.prt5`` particle file paths."""
        return list(self.particle_files)

    def find_smv_device(self, device_name: str) -> Optional[Any]:
        """
        Return the :class:`SmvDevice` location record for *device_name*, or None.

        Device location data is only available when the index was built from
        (or with) a ``.smv`` file.
        """
        return self.smv_devices.get(device_name)

    def device_locations(self) -> Dict[str, Any]:
        """Return all SMV device location records as ``{name: SmvDevice}``."""
        return dict(self.smv_devices)

    def find_device_file(self, device_name: str) -> Optional[str]:
        """Return the filepath of the CSV containing *device_name*, or None."""
        for df in self.device_files:
            if device_name in df.device_names:
                return df.filepath
        return None

    def read_device(self, device_name: str):
        """
        Convenience: read time-series for *device_name*.

        Returns ``ReaderResult`` or ``None`` if the device is not found.
        """
        filepath = self.find_device_file(device_name)
        if filepath is None:
            return None
        all_results = DeviceReader().read(filepath)
        return all_results.get(device_name)

    def summary(self) -> str:
        lines = [
            f"ResultIndex — {self.output_dir}",
            f"  CHID        : {self.chid}",
            f"  SMV file    : {self.smv_filepath or '(none)'}",
            f"  Meshes (SMV): {len(self.smv_grids)}",
            f"  Completed   : {self.stats.completed}",
            f"  T reached   : {self.stats.t_reached:.1f} s",
            f"  Wall time   : {self.stats.wall_time_seconds:.1f} s",
            f"  Devices     : {len(self.all_device_names())} CSV  "
                             f"/ {len(self.smv_devices)} SMV locations",
            f"  Slice files : {len(self.slice_index)}",
            f"  Slice qty   : {self.slice_quantities()}",
            f"  Bound files : {len(self.boundary_index)}",
            f"  Bound qty   : {self.boundary_quantities()}",
            f"  Plot3D files: {len(self.plot3d_files)}",
            f"  Part. files : {len(self.particle_files)}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<ResultIndex chid={self.chid!r} "
                f"slices={len(self.slice_index)} "
                f"boundaries={len(self.boundary_index)} "
                f"plot3d={len(self.plot3d_files)} "
                f"particles={len(self.particle_files)} "
                f"completed={self.stats.completed}>")

    # ── Archive / restore ──────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialise index metadata to a JSON-compatible dict (no binary data)."""
        s = self.stats
        return {
            "output_dir": self.output_dir,
            "chid": self.chid,
            "smv_filepath": self.smv_filepath,
            "stats": {
                "chid": s.chid, "title": s.title, "fds_version": s.fds_version,
                "mpi_processes": s.mpi_processes, "openmp_threads": s.openmp_threads,
                "t_begin": s.t_begin, "t_end": s.t_end, "t_reached": s.t_reached,
                "total_cells": s.total_cells, "mesh_count": s.mesh_count,
                "wall_time_seconds": s.wall_time_seconds, "completed": s.completed,
                "error_lines": list(s.error_lines), "warning_lines": list(s.warning_lines),
            },
            "device_files": [
                {"filepath": df.filepath, "chid": df.chid, "device_names": list(df.device_names)}
                for df in self.device_files
            ],
            "slice_entries": [
                {
                    "filepath": e.filepath, "quantity": e.quantity,
                    "short_name": e.short_name, "units": e.units, "mesh_id": e.mesh_id,
                    "i1": e.i1, "i2": e.i2, "j1": e.j1, "j2": e.j2, "k1": e.k1, "k2": e.k2,
                }
                for e in self.slice_index.all_entries()
            ],
            "boundary_entries": [
                {
                    "filepath": e.filepath, "quantity": e.quantity,
                    "short_name": e.short_name, "units": e.units,
                    "mesh_id": e.mesh_id, "n_patches": e.n_patches,
                }
                for e in self.boundary_index.all_entries()
            ],
            "plot3d_files": list(self.plot3d_files),
            "particle_files": list(self.particle_files),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ResultIndex":
        """Restore an index from a dict produced by :meth:`to_dict`."""
        idx = cls()
        idx.output_dir   = d.get("output_dir", "")
        idx.chid         = d.get("chid", "")
        idx.smv_filepath = d.get("smv_filepath")

        s = d.get("stats", {})
        idx.stats = SimulationStats(
            chid=s.get("chid", ""), title=s.get("title", ""),
            fds_version=s.get("fds_version", ""),
            mpi_processes=s.get("mpi_processes", 1),
            openmp_threads=s.get("openmp_threads", 1),
            t_begin=s.get("t_begin", 0.0), t_end=s.get("t_end", 0.0),
            t_reached=s.get("t_reached", 0.0),
            total_cells=s.get("total_cells", 0), mesh_count=s.get("mesh_count", 0),
            wall_time_seconds=s.get("wall_time_seconds", 0.0),
            completed=s.get("completed", False),
            error_lines=list(s.get("error_lines", [])),
            warning_lines=list(s.get("warning_lines", [])),
        )

        idx.device_files = [
            DeviceFile(
                filepath=df["filepath"], chid=df["chid"],
                device_names=list(df.get("device_names", [])),
            )
            for df in d.get("device_files", [])
        ]

        for e in d.get("slice_entries", []):
            idx.slice_index._entries.append(SliceIndexEntry(
                filepath=e["filepath"], quantity=e["quantity"],
                short_name=e["short_name"], units=e["units"],
                mesh_id=e.get("mesh_id"),
                i1=e["i1"], i2=e["i2"], j1=e["j1"], j2=e["j2"],
                k1=e["k1"], k2=e["k2"],
            ))

        for e in d.get("boundary_entries", []):
            idx.boundary_index._entries.append(BoundaryIndexEntry(
                filepath=e["filepath"], quantity=e["quantity"],
                short_name=e["short_name"], units=e["units"],
                mesh_id=e.get("mesh_id"), n_patches=e.get("n_patches", 0),
            ))

        idx.plot3d_files  = list(d.get("plot3d_files", []))
        idx.particle_files = list(d.get("particle_files", []))
        return idx

    def save(self, filepath: str) -> None:
        """Serialise this index to a JSON file at *filepath*."""
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        logger.info("ResultIndex saved to %s", filepath)

    @classmethod
    def load(cls, filepath: str) -> "ResultIndex":
        """Load an index previously saved with :meth:`save`."""
        with open(filepath, encoding="utf-8") as fh:
            d = json.load(fh)
        idx = cls.from_dict(d)
        logger.info("ResultIndex loaded from %s", filepath)
        return idx
