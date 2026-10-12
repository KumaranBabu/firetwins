"""
PyFDS FDS Formatting Utilities
================================
Functions for converting Python values to correctly-formatted FDS
namelist field strings.

All output strings are compatible with NIST FDS input file syntax.
"""
from __future__ import annotations

from typing import List, Optional


def fmt_float(value: float, precision: int = 4) -> str:
    """Format a float for FDS output, stripping unnecessary trailing zeros."""
    formatted = f"{value:.{precision}f}"
    # Strip trailing zeros but keep at least one decimal place
    formatted = formatted.rstrip("0").rstrip(".")
    if "." not in formatted:
        formatted += ".0"
    return formatted


def fmt_xb(xb: List[float], precision: int = 4) -> str:
    """Format a 6-element XB list as ``XB=x1,x2,y1,y2,z1,z2``."""
    if len(xb) != 6:
        raise ValueError(f"XB must have 6 elements, got {len(xb)}")
    vals = ",".join(fmt_float(v, precision) for v in xb)
    return f"XB={vals}"


def fmt_ijk(ijk: List[int]) -> str:
    """Format a 3-element IJK list as ``IJK=i,j,k``."""
    if len(ijk) != 3:
        raise ValueError(f"IJK must have 3 elements, got {len(ijk)}")
    return f"IJK={ijk[0]},{ijk[1]},{ijk[2]}"


def fmt_xyz(xyz: List[float], precision: int = 4) -> str:
    """Format a 3-element XYZ list as ``XYZ=x,y,z``."""
    if len(xyz) != 3:
        raise ValueError(f"XYZ must have 3 elements, got {len(xyz)}")
    vals = ",".join(fmt_float(v, precision) for v in xyz)
    return f"XYZ={vals}"


def fds_bool(value: bool) -> str:
    """Convert a Python bool to FDS logical: ``.TRUE.`` or ``.FALSE.``"""
    return ".TRUE." if value else ".FALSE."


def fds_str(value: str) -> str:
    """Wrap a string in FDS single quotes: ``'value'``"""
    return f"'{value}'"


def fmt_rgb(rgb: List[float]) -> str:
    """
    Format an RGB triple (0–1 floats or 0–255 ints) as ``COLOR='R,G,B'``.

    Values > 1 are assumed to be 0–255 ints and passed through unchanged;
    values ≤ 1 are scaled to 0–255.
    """
    if len(rgb) != 3:
        raise ValueError(f"RGB must have 3 elements, got {len(rgb)}")
    ints: List[int] = []
    for v in rgb:
        ints.append(round(v * 255) if v <= 1.0 else int(v))
    return f"COLOR='{ints[0]},{ints[1]},{ints[2]}'"


def fmt_namelist(tag: str, fields: dict, indent: int = 4) -> str:
    """
    Render an FDS namelist block from a tag name and field dictionary.

    Parameters
    ----------
    tag : str
        FDS namelist keyword, e.g. ``'MESH'``, ``'SURF'``.
    fields : dict
        Mapping of FDS field name → already-formatted string value.
        Pass pre-formatted strings (e.g. output of ``fmt_xb``).
    indent : int
        Spaces to indent field lines after the first.

    Returns
    -------
    str
        Multi-line FDS namelist string ending with ``/``.

    Example::

        print(fmt_namelist("MESH", {
            "ID":  fds_str("MESH01"),
            "IJK": "20,20,10",
            "XB":  "0.0,4.0,0.0,4.0,0.0,2.0",
        }))
        # &MESH ID='MESH01', IJK=20,20,10,
        #        XB=0.0,4.0,0.0,4.0,0.0,2.0 /
    """
    if not fields:
        return f"&{tag} /"
    pad = " " * (len(tag) + 2 + indent)   # align continuation lines
    pairs = [f"{k}={v}" for k, v in fields.items()]
    # First field on same line as &TAG
    lines  = [f"&{tag} {pairs[0]},"]
    for pair in pairs[1:-1]:
        lines.append(f"{pad}{pair},")
    if len(pairs) > 1:
        lines.append(f"{pad}{pairs[-1]} /")
    else:
        # Only one field — fix the trailing comma on the first line
        lines[0] = lines[0].rstrip(",") + " /"
    return "\n".join(lines)


def cell_size_label(dx: float) -> str:
    """Return a human-readable cell size label, e.g. ``'50mm'``, ``'0.1m'``."""
    if dx < 0.01:
        return f"{dx * 1000:.1f}mm"
    if dx < 1.0:
        return f"{dx * 100:.0f}cm"
    return f"{dx:.2f}m"
