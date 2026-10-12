"""FDS log (.out) parser."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
