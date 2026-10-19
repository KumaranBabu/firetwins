"""FDS ``&CTRL`` function types (FUNCTION_TYPE) and what each one needs.

``Control.function_type`` stays a plain string so that imported files with newer
or unusual values still load; the API and the validation rule use this table.
Source: FDS User Guide, "Control Functions" (FDS 6.7-6.9).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ControlFunction:
    name: str
    description: str
    #: "any" = at least one INPUT_ID, "one" = exactly one, "none" = no input needed
    inputs: str = "any"
    #: parameters that must be set for the function to mean anything
    required: Tuple[str, ...] = ()
    #: PyroSim control kind this belongs to (UI grouping)
    kind: str = "Custom"


_FUNCTIONS = [
    ControlFunction("ANY", "On when any input is on", "any", (), "Detector-based"),
    ControlFunction("ALL", "On when all inputs are on", "any", (), "Detector-based"),
    ControlFunction("ONLY", "On when exactly N inputs are on", "any", ("n",), "Detector-based"),
    ControlFunction("AT_LEAST", "On when at least N inputs are on", "any", ("n",), "Detector-based"),
    ControlFunction("TIME_DELAY", "Output follows the input after a delay", "one", ("delay",), "Time-based"),
    ControlFunction("DEADBAND", "Thermostat: switch between two set points", "one", ("deadband",), "Deadband-based"),
    ControlFunction("KILL", "Stops the run when the input turns on", "one", (), "Custom"),
    ControlFunction("RESTART", "Writes a restart file when the input turns on", "one", (), "Custom"),
    ControlFunction("CUSTOM", "Output defined by a RAMP of the input", "one", ("ramp_id",), "Custom"),
    ControlFunction("SUM", "Sum of inputs", "any", (), "Mathematical"),
    ControlFunction("SUBTRACT", "First input minus the others", "any", (), "Mathematical"),
    ControlFunction("MULTIPLY", "Product of inputs", "any", (), "Mathematical"),
    ControlFunction("DIVIDE", "First input divided by the others", "any", (), "Mathematical"),
    ControlFunction("POWER", "First input raised to the second", "any", (), "Mathematical"),
    ControlFunction("EXP", "Exponential of the input", "one", (), "Mathematical"),
    ControlFunction("LOG", "Natural logarithm of the input", "one", (), "Mathematical"),
    ControlFunction("COS", "Cosine of the input", "one", (), "Mathematical"),
    ControlFunction("SIN", "Sine of the input", "one", (), "Mathematical"),
    ControlFunction("ACOS", "Arccosine of the input", "one", (), "Mathematical"),
    ControlFunction("ASIN", "Arcsine of the input", "one", (), "Mathematical"),
    ControlFunction("ATAN", "Arctangent of the input", "one", (), "Mathematical"),
    ControlFunction("MAX", "Largest of the inputs", "any", (), "Mathematical"),
    ControlFunction("MIN", "Smallest of the inputs", "any", (), "Mathematical"),
    ControlFunction("PERCENTILE", "Value of a profile below which a given fraction of the total lies (flame height from a vertical profile)",
                    "one", ("percentile_rank",), "Mathematical"),
    ControlFunction("PID", "PID controller on one input (target value and three gains)", "one", (), "Mathematical"),
]

CONTROL_FUNCTIONS: Dict[str, ControlFunction] = {f.name: f for f in _FUNCTIONS}


def list_control_functions() -> List[str]:
    return [f.name for f in _FUNCTIONS]


def get_control_function(name: str) -> Optional[ControlFunction]:
    return CONTROL_FUNCTIONS.get((name or "").strip().upper())


def problems(control) -> List[str]:
    """Human-readable problems with a ``Control`` (empty list = fine)."""
    out: List[str] = []
    fn = get_control_function(control.function_type)
    if fn is None:
        return [f"unknown FUNCTION_TYPE {control.function_type!r} "
                f"(expected one of {', '.join(list_control_functions())})"]
    ids = list(control.input_ids or ([control.input_id] if control.input_id else []))
    if fn.inputs == "one" and len(ids) != 1:
        out.append(f"{fn.name} needs exactly one INPUT_ID (has {len(ids)})")
    elif fn.inputs == "any" and not ids:
        out.append(f"{fn.name} needs at least one INPUT_ID")
    for attr in fn.required:
        if getattr(control, attr, None) in (None, ""):
            out.append(f"{fn.name} needs {attr.upper()}")
    return out
