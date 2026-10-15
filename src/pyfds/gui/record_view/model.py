"""Record View logic (plan step F4), free of Qt: which line of the FDS text belongs to which object."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# FDS namelist -> the api collection that holds those objects.
TAG_TO_ATTR = {
    "MESH": "meshes", "OBST": "obstructions", "VENT": "vents", "HOLE": "holes", "SURF": "surfaces",
    "MATL": "materials", "REAC": "reactions", "DEVC": "devices", "RAMP": "ramps", "SPEC": "species",
    "ZONE": "zones", "PART": "particles", "INIT": "inits", "CTRL": "controls", "PROP": "props",
    "SLCF": "slices", "BNDF": "bndfs", "ISOF": "isofs", "PL3D": "plot3ds", "PROF": "profs",
    "GEOM": "geom",
}
_TAG = re.compile(r"^\s*&(\w+)")
_ID = re.compile(r"\bID\s*=\s*'([^']*)'", re.IGNORECASE)


@dataclass(frozen=True)
class RecordLine:
    line: int                     # 0-based line number in the text
    tag: str                      # HEAD, OBST ...
    name: Optional[str]           # the ID, if the record has one
    attr: Optional[str]           # api collection, if we know the namelist


def index_records(text: str) -> List[RecordLine]:
    """One entry per line that starts a namelist record."""
    out: List[RecordLine] = []
    for n, line in enumerate(text.split("\n")):
        m = _TAG.match(line)
        if not m:
            continue
        tag = m.group(1).upper()
        ident = _ID.search(line)
        out.append(RecordLine(n, tag, ident.group(1) if ident else None, TAG_TO_ATTR.get(tag)))
    return out


def record_at(records: List[RecordLine], line: int) -> Optional[RecordLine]:
    """The record a line belongs to (a record is one line, so this is an exact match)."""
    return next((r for r in records if r.line == line), None)


def entity_for(api: Any, record: RecordLine) -> Optional[Any]:
    """The object a record was written from, or None (HEAD, TIME ... or an unknown ID)."""
    if record.attr is None or record.name is None:
        return None
    try:
        return next((e for e in getattr(api, record.attr).all() if getattr(e, "name", None) == record.name), None)
    except AttributeError:
        return None


def lines_of(records: List[RecordLine], attr: str, name: str) -> List[int]:
    """Every line of an object's record(s) (a ramp has one per point)."""
    return [r.line for r in records if r.attr == attr and r.name == name]


def summary(records: List[RecordLine]) -> Dict[str, int]:
    """``{namelist: how many records}`` for the status line."""
    out: Dict[str, int] = {}
    for r in records:
        out[r.tag] = out.get(r.tag, 0) + 1
    return out
