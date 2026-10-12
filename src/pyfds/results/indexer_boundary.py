"""Boundary file index and device file record."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .reader import BoundaryReader

logger = logging.getLogger(__name__)


_BF_MESH_RE  = re.compile(r'_(\d+)\.bf$', re.IGNORECASE)


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


@dataclass
class DeviceFile:
    filepath: str
    chid: str
    device_names: List[str] = field(default_factory=list)
