"""Number formatting and small helpers shared by the FDS writer parts."""
from __future__ import annotations

import contextvars
from typing import Any, Dict, Optional

from pyfds.io.namelist import tokenize


def _fds_bool(v: bool) -> str:
    return ".TRUE." if v else ".FALSE."


def _fmt(v: Any) -> str:
    """Format any Python value as a Fortran namelist token."""
    if isinstance(v, bool):
        return _fds_bool(v)
    if isinstance(v, (list, tuple)):
        parts = []
        for item in v:
            if isinstance(item, bool):
                parts.append(_fds_bool(item))
            elif isinstance(item, str):
                parts.append(f"'{item}'" if not item.startswith("'") else item)
            elif isinstance(item, float):
                parts.append(_fmt_float(item))
            else:
                parts.append(str(item))
        return ",".join(parts)
    if isinstance(v, str):
        return f"'{v}'" if not (v.startswith("'") or v.startswith(".")) else v
    if isinstance(v, float):
        return _fmt_float(v)
    return str(v)


_NUMFMT: "contextvars.ContextVar" = contextvars.ContextVar("pyfds_numfmt", default=None)


NUMBER_STYLES = ("auto", "decimal", "scientific")


def check_number_format(fmt: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Validate ``{"significant_digits": 1..15 or None, "style": auto|decimal|scientific}``."""
    if fmt is None:
        return None
    unknown = set(fmt) - {"significant_digits", "style"}
    if unknown:
        raise ValueError(f"unknown number-format keys: {sorted(unknown)}")
    n, style = fmt.get("significant_digits"), fmt.get("style", "auto")
    if n is not None and (not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 15):
        raise ValueError("significant_digits must be a whole number from 1 to 15")
    if style not in NUMBER_STYLES:
        raise ValueError(f"style must be one of {', '.join(NUMBER_STYLES)}")
    return {"significant_digits": n, "style": style}


def _fmt_float(v: float) -> str:
    """Produce decimal notation FDS can reliably parse (no scientific notation gotchas)."""
    fmt = _NUMFMT.get()
    if fmt is not None and v != 0.0:
        n, style = fmt["significant_digits"], fmt["style"]
        if style == "scientific":
            return f"{v:.{(n or 6) - 1}E}".replace("E+0", "E+").replace("E-0", "E-")
        if n is not None:
            if style == "decimal" or 0.0001 <= abs(v) <= 999999.0:
                text = f"{v:.{n}g}"
                if "e" in text or "E" in text:          # %g switched to exponent: write it out in full
                    from decimal import Decimal
                    text = format(Decimal(text), "f")
                return text if "." in text else text + ".0"
            return f"{v:.{n - 1}E}".replace("E+0", "E+").replace("E-0", "E-")
    if v == 0.0:
        return "0.0"
    abs_v = abs(v)
    if 0.0001 <= abs_v <= 999999.0:
        if abs_v >= 100:
            return f"{v:.2f}"
        if abs_v >= 1:
            result = f"{v:.5f}".rstrip("0").rstrip(".")
            return result if "." in result else result + ".0"
        result = f"{v:.7f}".rstrip("0").rstrip(".")
        return result if "." in result else result + ".0"
    # Very large / small -> explicit scientific
    return f"{v:.6E}".replace("E+0", "E+").replace("E-0", "E-")


def _nl(tag: str, parts: Dict[str, Any]) -> str:
    """Build a single FDS namelist line: &TAG K1=V1, K2=V2 /"""
    tokens = [f"{k.upper()}={_fmt(v)}" for k, v in parts.items() if v is not None]
    return f"&{tag.upper()} {', '.join(tokens)} /"


def _with_extra(line: str, extra) -> str:
    """Merge pass-through parameters (``fds_extra``) into a namelist line.

    An extra with the same key as one the writer already produced *replaces*
    it (the value read from the source file is the truth), so a key never
    appears twice.
    """
    if not extra or not line.endswith(" /"):
        return line
    rec = next(tokenize(line))
    merged = dict(rec.fields)
    merged.update(extra)
    return f"&{rec.tag} " + ", ".join(f"{k}={v}" for k, v in merged.items()) + " /"


_VERSION_ORDER = {"6.7": 67, "6.8": 68, "6.9": 69, "latest": 999}
