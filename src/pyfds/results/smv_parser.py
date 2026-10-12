"""
PyFDS SMV Metadata Parser
==========================
Parses the ``.smv`` metadata file produced by FDS, extracting mesh
geometry, linked output files, and visualization object descriptors.

Supported sections
------------------
GRID / PDIM / TRNX / TRNY / TRNZ   — mesh geometry
SLCF                                — slice file references
BNDF                                — boundary file references
ISOF                                — isosurface file references
PL3D                                — Plot3D file references
DEVICE / SMOKEDEVICE                — device/sensor locations
PART                                — particle file references
S3D                                 — smoke-3D file references
OFFSET / VIEWPOINT                  — camera/scene settings

Example::

    from pyfds.results.smv_parser import SmvParser

    meta = SmvParser().parse("case.smv")
    print(meta.grids)
    print(meta.slices)
    print(meta.devices)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .smv_parser_model import (  # noqa: F401  (re-exported)
    SmvBoundary,
    SmvDevice,
    SmvGrid,
    SmvIsosurface,
    SmvMetadata,
    SmvParticle,
    SmvPlot3D,
    SmvSlice,
    SmvSmoke3D,
    SmvSurface,
    SmvViewpoint,
)
from .smv_parser_blocks import (  # noqa: F401  (re-exported)
    SmvParserBlocksMixin,
)
from .smv_parser_views import (  # noqa: F401  (re-exported)
    SmvParserViewsMixin,
)

from .smv_parser_model import (  # noqa: F401  (re-exported)
    SmvBoundary,
    SmvDevice,
    SmvGrid,
    SmvIsosurface,
    SmvParticle,
    SmvPlot3D,
    SmvSlice,
    SmvSmoke3D,
    SmvSurface,
    SmvViewpoint,
)


logger = logging.getLogger(__name__)


class SmvParser(SmvParserBlocksMixin, SmvParserViewsMixin):
    """
    Parses a FDS ``.smv`` file into ``SmvMetadata``.

    The SMV format is line-oriented with keyword/section blocks.
    This parser does a single forward pass, accumulating sections by
    keyword and then dispatching to typed handlers.
    """

    def parse(self, filepath: str) -> SmvMetadata:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"SMV file not found: {filepath}")

        meta = SmvMetadata(smv_filepath=str(path))
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

        self._first_pass(lines, meta)
        logger.info("SmvParser: %s  grids=%d  slices=%d  bndf=%d  devices=%d",
                    filepath, len(meta.grids), len(meta.slices),
                    len(meta.boundaries), len(meta.devices))
        return meta

    def _first_pass(self, lines: List[str], meta: SmvMetadata) -> None:
        i = 0
        n = len(lines)
        mesh_count = 0

        while i < n:
            raw = lines[i].rstrip()
            token = raw.strip().upper()
            i += 1

            if token.startswith("CHID"):
                meta.chid = raw.split(None, 1)[1].strip() if len(raw.split()) > 1 else ""
            elif token.startswith("TITLE"):
                meta.title = raw.split(None, 1)[1].strip() if len(raw.split()) > 1 else ""
            elif token.startswith("VERSION"):
                meta.fds_version = raw.split(None, 1)[1].strip() if len(raw.split()) > 1 else ""
            elif token == "GRID":
                mesh_count += 1
                i = self._parse_grid(lines, i, mesh_count, meta)
            elif token in ("SLCF", "SLCC"):
                cell_centred = token == "SLCC"
                i = self._parse_slcf(lines, i, mesh_count, cell_centred, meta)
            elif token == "BNDF":
                i = self._parse_bndf(lines, i, mesh_count, meta)
            elif token == "ISOF":
                i = self._parse_isof(lines, i, mesh_count, meta)
            elif token == "PL3D":
                i = self._parse_pl3d(lines, i, mesh_count, meta)
            elif token in ("SMOKF3D", "S3D"):
                i = self._parse_s3d(lines, i, mesh_count, meta)
            elif token == "PART":
                i = self._parse_part(lines, i, mesh_count, meta)
            elif token in ("DEVICE", "SMOKEDEVICE"):
                i = self._parse_device(lines, i, meta)
            elif token == "OFFSET":
                i = self._parse_offset(lines, i, meta)
            elif token == "VIEWPOINT":
                i = self._parse_viewpoint(lines, i, raw, meta)
            elif token in ("TRNX", "TRNY", "TRNZ"):
                axis = token[-1].lower()   # 'x', 'y', or 'z'
                i = self._parse_trn(lines, i, axis, mesh_count, meta)
            elif token == "SURFACE":
                i = self._parse_surface_record(lines, i, meta)
