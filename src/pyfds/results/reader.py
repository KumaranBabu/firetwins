"""
PyFDS Results Reader
====================
Post-processing readers for all FDS/Smokeview output file types.

Readers
-------
DeviceReader    — parses ``*_devc.csv`` (device time-series)
LogParser       — parses ``*.out`` (FDS console log / completion info)
SliceReader     — reads ``*.sf`` binary slice files (Fortran unformatted)
BoundaryReader  — reads ``*.bf`` binary boundary files (Fortran unformatted)

All readers return typed ``ReaderResult`` containers; raw numpy arrays are
exposed for downstream analysis or GUI plotting.
"""
from __future__ import annotations

import csv
import logging
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import numpy as np

from pyfds.core.exceptions import FdsBinaryError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Common data container
# ---------------------------------------------------------------------------

@dataclass
class ReaderResult:
    """Generic container returned by all readers."""
    source_file: str
    quantity: str = ""
    units: str = ""
    times: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    data: Any = None          # shape depends on reader (1-D, 3-D, ...)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_times(self) -> int:
        return len(self.times)

    @property
    def time(self):
        """Backward-compat alias for ``times``."""
        return self.times

    @property
    def values(self):
        """Backward-compat alias for ``data``."""
        return self.data


# ---------------------------------------------------------------------------
# DeviceReader — *_devc.csv
# ---------------------------------------------------------------------------

class DeviceReader:
    """
    Parse FDS device output CSV files (``<CHID>_devc.csv``).

    The first row of the CSV is the quantity/label row; the second row is
    the units row; subsequent rows are numeric time-series data.

    Example::

        reader = DeviceReader()
        results = reader.read("case_devc.csv")
        # results["Time"]        → ReaderResult  (times vector)
        # results["SPRK_01"]     → ReaderResult  (single device)
    """

    @classmethod
    def read(cls, filepath: str) -> Dict[str, ReaderResult]:
        """
        Read a ``*_devc.csv`` file.

        Returns
        -------
        dict
            Mapping ``device_name → ReaderResult``.  The ``"Time"`` key
            always contains the simulation time axis.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Device CSV not found: {filepath}")

        results: Dict[str, ReaderResult] = {}
        try:
            with path.open(newline="", encoding="utf-8-sig") as fh:
                reader = csv.reader(fh)
                rows = list(reader)

            if len(rows) < 3:
                logger.warning("DeviceReader: too few rows in %s", filepath)
                return results

            # Row 0: column headers (device names / "Time")
            # Row 1: units
            headers = [h.strip() for h in rows[0]]
            units   = [u.strip() for u in rows[1]]
            # Real FDS writes the UNITS row first and the names row ("Time", "HRR", ...) second;
            # older/hand-made files have them the other way round. Go by where "Time" is.
            if headers and units and units[0].lower() == "time" and headers[0].lower() != "time":
                headers, units = units, headers

            # Remaining rows: numeric data
            data_rows = rows[2:]
            if not data_rows:
                return results

            n_cols = len(headers)
            columns: List[List[float]] = [[] for _ in range(n_cols)]

            for row in data_rows:
                for i, val in enumerate(row[:n_cols]):
                    try:
                        columns[i].append(float(val))
                    except ValueError:
                        columns[i].append(float("nan"))

            time_arr = np.array(columns[0], dtype=float)

            for i, name in enumerate(headers):
                arr = np.array(columns[i], dtype=float)
                results[name] = ReaderResult(
                    source_file=str(path),
                    quantity=name,
                    units=units[i] if i < len(units) else "",
                    times=time_arr,
                    data=arr,
                )

            logger.info("DeviceReader: read %d devices from %s", n_cols - 1, filepath)
        except Exception as exc:
            logger.error("DeviceReader: failed reading %s: %s", filepath, exc)
            raise

        return results

    def read_device(self, filepath: str, device_name: str) -> Optional[ReaderResult]:
        """Convenience: read a single device by name."""
        all_results = self.read(filepath)
        return all_results.get(device_name)

    def find_csv(self, output_dir: str, chid: str) -> Optional[str]:
        """Locate ``<CHID>_devc.csv`` in *output_dir*."""
        p = Path(output_dir) / f"{chid}_devc.csv"
        return str(p) if p.exists() else None


# ---------------------------------------------------------------------------
# LogParser — *.out
# ---------------------------------------------------------------------------

@dataclass
class SimulationStats:
    """Summary statistics extracted from the FDS .out file."""
    chid: str = ""
    title: str = ""
    fds_version: str = ""
    mpi_processes: int = 1
    openmp_threads: int = 1
    t_begin: float = 0.0
    t_end: float = 0.0
    t_reached: float = 0.0
    total_cells: int = 0
    mesh_count: int = 0
    wall_time_seconds: float = 0.0
    completed: bool = False
    error_lines: List[str] = field(default_factory=list)
    warning_lines: List[str] = field(default_factory=list)

    @property
    def version(self) -> str:
        """Alias for ``fds_version``."""
        return self.fds_version

    @property
    def wall_time(self) -> float:
        """Alias for ``wall_time_seconds``."""
        return self.wall_time_seconds


class LogParser:
    """
    Parse a FDS ``.out`` console log file.

    Extracts version, run parameters, mesh/cell counts, timing data,
    errors, and warnings.

    Example::

        parser = LogParser()
        stats = parser.parse("case.out")
        print(stats.completed, stats.wall_time_seconds)
    """

    # Compiled patterns — flexible enough to match both verbose and compact FDS logs
    _RE_VERSION   = re.compile(r'FDS\s+Version\s*[:\s]+([\d.]+)', re.IGNORECASE)
    _RE_CHID      = re.compile(r'CHID\s*[:=]\s*(\S+)', re.IGNORECASE)
    _RE_TITLE     = re.compile(r'TITLE\s*[:=]\s*(.*)', re.IGNORECASE)
    _RE_TEND_KW   = re.compile(r'T_END\s*=\s*([\d.]+)', re.IGNORECASE)
    _RE_TEND_FULL = re.compile(r'Simulation\s+Start.*?:\s*([\d.]+).*?End.*?:\s*([\d.]+)',
                               re.IGNORECASE | re.DOTALL)
    _RE_STEP_T    = re.compile(r'Step:\s*\d+\s+T:\s*([\d.]+)', re.IGNORECASE)
    _RE_CELLS     = re.compile(r'Total\s+Cells\s*[=:]\s*(\d+)', re.IGNORECASE)
    _RE_MESH_N    = re.compile(r'Number\s+of\s+Meshes\s*[=:]\s*(\d+)', re.IGNORECASE)
    _RE_MPI       = re.compile(r'MPI\s+Processes\s*[=:]\s*(\d+)', re.IGNORECASE)
    _RE_OMP       = re.compile(r'OpenMP\s+Threads\s*[=:]\s*(\d+)', re.IGNORECASE)
    _RE_WALL      = re.compile(r'(?:Total\s+Time\s+\(s\)|wall\s+clock\s+time)\s*[=:]\s*([\d.]+)',
                               re.IGNORECASE)
    _RE_DONE      = re.compile(r'(?:STOP:\s*FDS\s+completed\s+successfully'
                               r'|Simulation\s+completed\s+successfully)',
                               re.IGNORECASE)
    _RE_ERROR     = re.compile(r'\bERROR\b', re.IGNORECASE)
    _RE_WARNING   = re.compile(r'\bWARNING\b', re.IGNORECASE)

    @classmethod
    def parse(cls, filepath: str) -> SimulationStats:
        """
        Parse *filepath* and return a ``SimulationStats``.

        Raises ``FileNotFoundError`` if *filepath* does not exist.
        """
        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.error("LogParser: cannot read %s: %s", filepath, exc)
            raise

        stats = SimulationStats()
        lines = text.splitlines()

        last_t = 0.0
        for line in lines:
            if m := cls._RE_VERSION.search(line):
                stats.fds_version = m.group(1)
            if m := cls._RE_CHID.search(line):
                stats.chid = m.group(1)
            if m := cls._RE_TITLE.search(line):
                stats.title = m.group(1).strip()
            if m := cls._RE_CELLS.search(line):
                stats.total_cells = int(m.group(1))
            if m := cls._RE_MESH_N.search(line):
                stats.mesh_count = int(m.group(1))
            if m := cls._RE_MPI.search(line):
                stats.mpi_processes = int(m.group(1))
            if m := cls._RE_OMP.search(line):
                stats.openmp_threads = int(m.group(1))
            if m := cls._RE_WALL.search(line):
                stats.wall_time_seconds = float(m.group(1))
            if m := cls._RE_STEP_T.search(line):
                last_t = float(m.group(1))
            if cls._RE_DONE.search(line):
                stats.completed = True
            if cls._RE_ERROR.search(line):
                stats.error_lines.append(line.strip())
            if cls._RE_WARNING.search(line):
                stats.warning_lines.append(line.strip())
            if m := cls._RE_TEND_KW.search(line):
                try:
                    stats.t_end = float(m.group(1))
                except ValueError:
                    pass

        stats.t_reached = last_t

        # Also try verbose start/end format (may span lines)
        if m := cls._RE_TEND_FULL.search(text):
            try:
                stats.t_begin = float(m.group(1))
                stats.t_end   = float(m.group(2))
            except ValueError:
                pass

        logger.info("LogParser: %s  completed=%s  t_reached=%.1f  wall=%.1fs",
                    filepath, stats.completed, stats.t_reached, stats.wall_time_seconds)
        return stats

    def check_status(self, filepath: str) -> Dict[str, Any]:
        """
        Backward-compat method: parse *filepath* and return a simple status dict.

        Returns
        -------
        dict with keys:
            ``completed`` (bool), ``error`` (str or None), ``steps`` (int)
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        completed = bool(re.search(
            r'(?:FDS\s+completed\s+successfully|Simulation\s+completed\s+successfully)',
            text, re.IGNORECASE))
        error: Optional[str] = None
        steps = 0
        for line in lines:
            if re.search(r'\bERROR\b', line, re.IGNORECASE):
                m = re.search(r'ERROR\s*[:\-]?\s*(.*)', line, re.IGNORECASE)
                if m and not error:
                    error = m.group(1).strip() or line.strip()
            if re.search(r'Time\s+Step', line, re.IGNORECASE):
                steps += 1
        return {"completed": completed, "error": error, "steps": steps}

    def find_out(self, output_dir: str, chid: str) -> Optional[str]:
        """Locate ``<CHID>.out`` in *output_dir*."""
        p = Path(output_dir) / f"{chid}.out"
        return str(p) if p.exists() else None


# ---------------------------------------------------------------------------
# Fortran unformatted binary helpers
# ---------------------------------------------------------------------------

def _read_record(fh) -> bytes:
    """
    Read one Fortran unformatted sequential record.

    Format: [int32 length] [data bytes] [int32 length]
    Raises ``FdsBinaryError`` on mismatch or EOF.
    """
    len_bytes = fh.read(4)
    if len(len_bytes) < 4:
        raise EOFError("Fortran record: unexpected EOF reading leading marker")
    length = struct.unpack("<i", len_bytes)[0]
    data = fh.read(length)
    if len(data) < length:
        raise EOFError(f"Fortran record: expected {length} bytes, got {len(data)}")
    trail = fh.read(4)
    if len(trail) < 4:
        raise EOFError("Fortran record: unexpected EOF reading trailing marker")
    trail_len = struct.unpack("<i", trail)[0]
    if trail_len != length:
        raise FdsBinaryError(
            filepath=getattr(fh, "name", "?"),
            offset=fh.tell(),
            message=f"Fortran record length mismatch: {length} vs {trail_len}",
        )
    return data


def _read_string_record(fh) -> str:
    """Read a Fortran string record, stripped of whitespace."""
    return _read_record(fh).decode("ascii", errors="replace").strip()


def _skip_string_records(fh, n: int) -> None:
    """Skip *n* Fortran string records (used to consume binary file headers)."""
    for _ in range(n):
        _read_record(fh)


# ---------------------------------------------------------------------------
# SliceReader — *.sf
# ---------------------------------------------------------------------------

@dataclass
class SliceFrame:
    """One time-step worth of slice data."""
    time: float
    data: np.ndarray       # shape (ni, nj, nk) or flattened; see header


@dataclass
class SliceHeader:
    quantity: str
    short_name: str
    units: str
    i1: int; i2: int
    j1: int; j2: int
    k1: int; k2: int

    @property
    def shape(self) -> Tuple[int, int, int]:
        return (self.i2 - self.i1 + 1,
                self.j2 - self.j1 + 1,
                self.k2 - self.k1 + 1)

    @property
    def n_values(self) -> int:
        ni, nj, nk = self.shape
        return ni * nj * nk


class SliceReader:
    """
    Read FDS slice files (``*.sf``).

    FDS slice binary layout (Fortran unformatted)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Record 1  — quantity string   (30 chars)
    Record 2  — short name string (30 chars)
    Record 3  — units string      (30 chars)
    Record 4  — i1, i2, j1, j2, k1, k2  (6 × int32)
    Then for each time step:
      Record 5n+0 — float32 time
      Record 5n+1 — float32 array (n_values floats)

    BUG-07 fix: the original ``smv_binary.py`` skipped only 1 string record
    and read the index record incorrectly. This implementation reads all 3
    string records then the index record before entering the frame loop.

    Example::

        reader = SliceReader()
        header, frames = reader.read("case_01.sf")
        print(header.quantity, header.units)
        for frame in frames:
            print(frame.time, frame.data.mean())
    """

    @classmethod
    def read(cls, filepath: str) -> ReaderResult:
        """
        Read all frames from *filepath* and return a ``ReaderResult``.

        ``result.times`` is a 1-D float array of frame times.
        ``result.data`` is a stacked array of shape ``(n_frames, ni, nj, nk)``.
        """
        header, frames = cls._read_raw(filepath)
        times_arr = np.array([f.time for f in frames], dtype=float)
        data_arr  = (np.stack([f.data for f in frames])
                     if frames else np.array([], dtype=float))
        return ReaderResult(
            source_file=str(filepath),
            quantity=header.quantity,
            units=header.units,
            times=times_arr,
            data=data_arr,
            metadata={"header": header},
        )

    @classmethod
    def _read_raw(cls, filepath: str) -> Tuple[SliceHeader, List[SliceFrame]]:
        """Internal: read header + all frames as raw objects."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Slice file not found: {filepath}")

        frames: List[SliceFrame] = []
        header: Optional[SliceHeader] = None
        try:
            with open(filepath, "rb") as fh:
                quantity   = _read_string_record(fh)
                short_name = _read_string_record(fh)
                units      = _read_string_record(fh)
                idx_data = _read_record(fh)
                i1, i2, j1, j2, k1, k2 = struct.unpack("<6i", idx_data)
                header = SliceHeader(
                    quantity=quantity, short_name=short_name, units=units,
                    i1=i1, i2=i2, j1=j1, j2=j2, k1=k1, k2=k2,
                )
                n_values = header.n_values
                while True:
                    try:
                        t_data = _read_record(fh)
                        time_val = struct.unpack("<f", t_data)[0]
                        arr_data = _read_record(fh)
                        arr = np.frombuffer(arr_data, dtype="<f4").astype(float)
                        arr = arr[:n_values].reshape(header.shape, order="F")
                        frames.append(SliceFrame(time=float(time_val), data=arr))
                    except EOFError:
                        break
        except FdsBinaryError:
            raise
        except Exception as exc:
            logger.error("SliceReader: error reading %s: %s", filepath, exc)
            raise

        logger.info("SliceReader: %s  qty=%r  frames=%d",
                    filepath, header.quantity if header else "?", len(frames))
        return header, frames

    def read_at_time(
        self,
        filepath: str,
        target_time: float,
        tolerance: float = 0.5,
    ) -> Tuple[SliceHeader, Optional[SliceFrame]]:
        """Return the frame closest to *target_time* within *tolerance* seconds."""
        header, frames = self._read_raw(filepath)
        if not frames:
            return header, None
        closest = min(frames, key=lambda f: abs(f.time - target_time))
        if abs(closest.time - target_time) > tolerance:
            return header, None
        return header, closest

    @classmethod
    def iter_frames(cls, filepath: str) -> Iterator[Tuple[float, Any]]:
        """
        Generator that yields ``(time, data)`` tuples without loading all frames
        into memory at once. Suitable for large files.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Slice file not found: {filepath}")

        with open(filepath, "rb") as fh:
            quantity   = _read_string_record(fh)
            short_name = _read_string_record(fh)
            units      = _read_string_record(fh)
            idx_data   = _read_record(fh)
            i1, i2, j1, j2, k1, k2 = struct.unpack("<6i", idx_data)

            header = SliceHeader(
                quantity=quantity, short_name=short_name, units=units,
                i1=i1, i2=i2, j1=j1, j2=j2, k1=k1, k2=k2,
            )
            n_values = header.n_values

            while True:
                try:
                    t_data   = _read_record(fh)
                    time_val = struct.unpack("<f", t_data)[0]
                    arr_data = _read_record(fh)
                    arr = np.frombuffer(arr_data, dtype="<f4").astype(float)
                    arr = arr[:n_values].reshape(header.shape, order="F")
                    yield float(time_val), arr
                except EOFError:
                    break


# ---------------------------------------------------------------------------
# BoundaryReader — *.bf
# ---------------------------------------------------------------------------

@dataclass
class BoundaryHeader:
    quantity: str
    short_name: str
    units: str
    n_patches: int


@dataclass
class BoundaryPatch:
    """One surface patch per mesh face."""
    i1: int; i2: int
    j1: int; j2: int
    k1: int; k2: int
    iblk: int       # mesh index


@dataclass
class BoundaryFrame:
    time: float
    patch_data: List[np.ndarray]   # one array per patch


class BoundaryReader:
    """
    Read FDS boundary files (``*.bf``).

    FDS boundary binary layout (Fortran unformatted)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Record 1  — quantity string (30 chars)
    Record 2  — short name     (30 chars)
    Record 3  — units          (30 chars)
    Record 4  — n_patches (int32)
    For each patch p (0..n_patches-1):
      Record 4+p — i1,i2,j1,j2,k1,k2,iblk (7×int32)
    Then for each time step:
      Record t*0 — float32 time
      For each patch p:
        Record t*p — float32 array of patch values

    Example::

        reader = BoundaryReader()
        header, patches, frames = reader.read("case_01.bf")
        for frame in frames:
            print(frame.time, [p.mean() for p in frame.patch_data])
    """

    def read(
        self, filepath: str
    ) -> Tuple[BoundaryHeader, List[BoundaryPatch], List[BoundaryFrame]]:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Boundary file not found: {filepath}")

        patches: List[BoundaryPatch] = []
        frames: List[BoundaryFrame] = []

        try:
            with open(filepath, "rb") as fh:
                quantity   = _read_string_record(fh)
                short_name = _read_string_record(fh)
                units      = _read_string_record(fh)

                np_data   = _read_record(fh)
                n_patches = struct.unpack("<i", np_data)[0]

                header = BoundaryHeader(
                    quantity=quantity, short_name=short_name,
                    units=units, n_patches=n_patches,
                )

                # Read patch geometry records
                patch_sizes: List[int] = []
                for _ in range(n_patches):
                    rec = _read_record(fh)
                    i1, i2, j1, j2, k1, k2, iblk = struct.unpack("<7i", rec)
                    patches.append(BoundaryPatch(
                        i1=i1, i2=i2, j1=j1, j2=j2, k1=k1, k2=k2, iblk=iblk,
                    ))
                    # size = product of dimensions
                    size = (i2 - i1 + 1) * (j2 - j1 + 1) * (k2 - k1 + 1)
                    patch_sizes.append(max(size, 1))

                # Frame loop
                while True:
                    try:
                        t_rec    = _read_record(fh)
                        time_val = struct.unpack("<f", t_rec)[0]
                        pd: List[np.ndarray] = []
                        for sz in patch_sizes:
                            arr_data = _read_record(fh)
                            arr = np.frombuffer(arr_data, dtype="<f4").astype(float)
                            pd.append(arr[:sz])
                        frames.append(BoundaryFrame(time=float(time_val), patch_data=pd))
                    except EOFError:
                        break

        except FdsBinaryError:
            raise
        except Exception as exc:
            logger.error("BoundaryReader: error reading %s: %s", filepath, exc)
            raise

        logger.info("BoundaryReader: %s  qty=%r  patches=%d  frames=%d",
                    filepath, header.quantity, n_patches, len(frames))
        return header, patches, frames
