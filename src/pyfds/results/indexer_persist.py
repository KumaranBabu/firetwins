"""ResultIndex: saving to and loading from the index file."""
from __future__ import annotations

from typing import TYPE_CHECKING

import logging
import json
from typing import Any, Dict

from .reader import SimulationStats

from .indexer_boundary import BoundaryIndexEntry, DeviceFile
from .indexer_slices import SliceIndexEntry

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .indexer import ResultIndex


class ResultIndexPersistMixin:
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
