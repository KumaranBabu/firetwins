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

import logging
from typing import Any, Dict, List, Optional

from .reader import SimulationStats

from .indexer_boundary import (  # noqa: F401  (re-exported)
    BoundaryIndex,
    BoundaryIndexEntry,
    DeviceFile,
    _BF_MESH_RE,
)
from .indexer_build import (  # noqa: F401  (re-exported)
    ResultIndexBuildMixin,
)
from .indexer_persist import (  # noqa: F401  (re-exported)
    ResultIndexPersistMixin,
)
from .indexer_query import (  # noqa: F401  (re-exported)
    ResultIndexQueryMixin,
)
from .indexer_slices import (  # noqa: F401  (re-exported)
    SliceIndex,
    SliceIndexEntry,
    _SF_MESH_RE,
)

from .indexer_slices import (  # noqa: F401  (re-exported)
    SliceIndexEntry,
    _SF_MESH_RE,
)
from .indexer_boundary import (  # noqa: F401  (re-exported)
    BoundaryIndexEntry,
    _BF_MESH_RE,
)


logger = logging.getLogger(__name__)


class ResultIndex(ResultIndexBuildMixin, ResultIndexQueryMixin, ResultIndexPersistMixin):
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
