"""The pyrolysis calculator behind Edit Materials (PyroSim's 'Edit Pyrolysis Reaction'), free of Qt.

Four ways to give a reaction its rate; each returns the field values to put on the reaction (A and E, or the reference
temperature / heating rate / range FDS turns into A and E itself) and a one-line note. The numerics are the api's;
nothing here changes the project.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

METHODS = {
    "match": "Match a rate curve (FDS works out A and E)",
    "fit": "Fit a measured rate curve",
    "peak": "From a TGA peak (Kissinger)",
    "direct": "Specify A and E",
}
_FIELDS = ("a", "e", "n_s", "reference_temperature", "heating_rate", "pyrolysis_range")


@dataclass
class CalcResult:
    values: Dict[str, Optional[float]] = field(default_factory=dict)   # reaction fields to set (None clears)
    note: str = ""


def _need(inputs: Dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if inputs.get(k) in (None, "")]
    if missing:
        raise ValueError("give " + ", ".join(missing))


def compute(api: Any, material: Any, method: str, inputs: Dict[str, Any]) -> CalcResult:
    """Run one method. Raises ``ValueError`` with a plain message when the inputs do not allow it."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}")
    n = float(inputs.get("n", 1.0) or 1.0)
    if n <= 0:
        raise ValueError("the reaction order must be positive")
    if method == "match":
        _need(inputs, "reference_temperature", "heating_rate", "pyrolysis_range")
        t, h, r = (float(inputs[k]) for k in ("reference_temperature", "heating_rate", "pyrolysis_range"))
        if h <= 0 or r <= 0:
            raise ValueError("the heating rate and the pyrolysis range must be positive")
        return CalcResult({"a": None, "e": None, "n_s": n, "reference_temperature": t, "heating_rate": h,
                           "pyrolysis_range": r},
                          f"FDS will fit the rate to peak at {t:g} C for {h:g} K/min over {r:g} K")
    if method == "direct":
        _need(inputs, "a", "e")
        a, e = float(inputs["a"]), float(inputs["e"])
        if a <= 0 or e <= 0:
            raise ValueError("A and E must be positive")
        return CalcResult({"a": a, "e": e, "n_s": n, "reference_temperature": None, "heating_rate": None,
                           "pyrolysis_range": None}, f"A = {a:.4g} 1/s, E = {e:.4g} J/mol")
    if method == "fit":
        temps, rates = inputs.get("temperatures"), inputs.get("rates")
        if not temps or not rates or len(temps) != len(rates):
            raise ValueError("give the same number of temperatures and rates (at least three)")
        fit = api.materials.fit_pyrolysis(material, temps, rates, n=n, remaining_mass=inputs.get("remaining_mass"),
                                          apply=False)
        return CalcResult({"a": fit["A"], "e": fit["E"], "n_s": n, "reference_temperature": None,
                           "heating_rate": None, "pyrolysis_range": None},
                          f"A = {fit['A']:.4g} 1/s, E = {fit['E']:.4g} J/mol, R2 = {fit['r2']:.3f}")
    _need(inputs, "heating_rate", "peak_temperature")
    others: Optional[Sequence[Sequence[float]]] = inputs.get("other_runs") or None
    res = api.materials.pyrolysis_from_peak(
        material, float(inputs["heating_rate"]), float(inputs["peak_temperature"]),
        activation_energy=float(inputs["e"]) if inputs.get("e") not in (None, "") else None,
        other_runs=others, n=n, apply=False)
    return CalcResult({"a": res["A"], "e": res["E"], "n_s": n, "reference_temperature": None, "heating_rate": None,
                       "pyrolysis_range": None}, f"A = {res['A']:.4g} 1/s, E = {res['E']:.4g} J/mol")


def parse_pairs(text: str) -> List[List[float]]:
    """Rows of numbers pasted as text ('420 0.001' / '420, 0.001'), one row per line."""
    rows = []
    for line in text.replace(";", "\n").splitlines():
        parts = [p for p in line.replace(",", " ").replace("\t", " ").split() if p]
        if not parts:
            continue
        try:
            rows.append([float(p) for p in parts])
        except ValueError:
            raise ValueError(f"cannot read a number in {line.strip()!r}") from None
    return rows
