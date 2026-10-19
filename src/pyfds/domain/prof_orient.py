"""Face orientation of a solid profile: PyroSim's ORIENT (``Z+``) against FDS's IOR (``3``)."""
from __future__ import annotations

from typing import Any, Dict

_AXIS = {"X": 1, "Y": 2, "Z": 3}


def prof_ior(direction: str) -> int:
    """``'Z+'`` -> 3, ``'x-'`` -> -1; a bare axis means the positive side. Anything else is 3 (the top of an object)."""
    text = str(direction or "").strip().upper()
    if text.lstrip("+-").isdigit() and text.lstrip("+-") in ("1", "2", "3"):
        return int(text)
    negative = text.endswith("-") or text.startswith("-")
    axis = _AXIS.get(text.strip("+-")[:1], 3)
    return -axis if negative else axis


def prof_direction(fields: Dict[str, Any]) -> str:
    """ORIENT text for a parsed &PROF (IOR; the older DIRECTION key of earlier PyFDS files is still read)."""
    ior = fields.get("IOR")
    try:
        n = int(float(str(ior).strip()))
    except (TypeError, ValueError):
        n = 0
    if n:
        return f"{'XYZ'[abs(n) - 1]}{'-' if n < 0 else '+'}"
    old = str(fields.get("DIRECTION", "") or "").strip().strip("'\"").upper()
    return (old + "+" if len(old) == 1 else old) if old else "Z+"
