"""ResultIndex: finding slices, boundaries, devices; summary."""
from __future__ import annotations

from typing import TYPE_CHECKING

from typing import Any, Dict, List, Optional

from .reader import DeviceReader

from .indexer_boundary import BoundaryIndexEntry
from .indexer_slices import SliceIndexEntry

if TYPE_CHECKING:
    from .indexer import ResultIndex


class ResultIndexQueryMixin:
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
