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

import logging

from .reader_devc import (  # noqa: F401  (re-exported)
    DeviceReader,
    ReaderResult,
)
from .reader_log import (  # noqa: F401  (re-exported)
    LogParser,
    SimulationStats,
)
from .reader_common import (  # noqa: F401  (re-exported)
    _read_record,
    _read_string_record,
    _skip_string_records,
)
from .reader_slice import (  # noqa: F401  (re-exported)
    SliceFrame,
    SliceHeader,
    SliceReader,
)
from .reader_boundary import (  # noqa: F401  (re-exported)
    BoundaryFrame,
    BoundaryHeader,
    BoundaryPatch,
    BoundaryReader,
)

from .reader_devc import (  # noqa: F401  (re-exported)
    DeviceReader,
    ReaderResult,
)
from .reader_log import (  # noqa: F401  (re-exported)
    LogParser,
    SimulationStats,
)
from .reader_common import (  # noqa: F401  (re-exported)
    _read_record,
    _read_string_record,
    _skip_string_records,
)
from .reader_slice import (  # noqa: F401  (re-exported)
    SliceFrame,
    SliceHeader,
    SliceReader,
)
from .reader_boundary import (  # noqa: F401  (re-exported)
    BoundaryFrame,
    BoundaryHeader,
    BoundaryPatch,
    BoundaryReader,
)


logger = logging.getLogger(__name__)
