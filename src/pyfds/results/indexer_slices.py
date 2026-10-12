"""Slice file index."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .reader import SliceReader

logger = logging.getLogger(__name__)


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
