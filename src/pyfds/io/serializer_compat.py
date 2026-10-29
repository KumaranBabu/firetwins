"""Loading projects saved by older PyFDS versions: values that meant something different then."""
from __future__ import annotations

from typing import Any, Dict


def legacy_pres(values: Dict[str, Any]) -> Dict[str, Any]:
    """&PRES saved before 2026-10-29 (recognised by its ``mach_number_limit`` field) held two fake defaults: a
    VELOCITY_TOLERANCE of 0.05 that was always written, and SOLVER='SCARC' that was never written. Map them to
    "not set" / FDS's FFT, which is what such a project meant (and, for the solver, what FDS actually ran)."""
    if "mach_number_limit" not in values:
        return values
    out = {k: v for k, v in values.items() if k not in ("mach_number_limit", "pressure_iterations")}
    if out.get("velocity_tolerance") == 0.05:
        out["velocity_tolerance"] = None
    if out.get("solver") == "SCARC":
        out["solver"] = "FFT"
    return out
