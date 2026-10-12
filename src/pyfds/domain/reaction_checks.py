"""Complex-stoichiometry reaction checks (RXN-01): species known, lengths match, mass balanced."""
from __future__ import annotations

from typing import List, Optional

#: Species FDS defines itself, with molecular weights (g/mol)
BUILTIN_MW = {
    "OXYGEN": 31.9988, "NITROGEN": 28.0134, "CARBON DIOXIDE": 44.0095, "CARBON MONOXIDE": 28.0101,
    "WATER VAPOR": 18.0153, "HYDROGEN": 2.0159, "SOOT": 12.011, "METHANE": 16.0425,
    "PROPANE": 44.0956, "ETHANE": 30.069, "ETHYLENE": 28.0532, "METHANOL": 32.0419,
    "ETHANOL": 46.0684, "HYDROGEN CYANIDE": 27.0253, "HYDROGEN CHLORIDE": 36.4606, "ACETYLENE": 26.0373,
    "N-HEPTANE": 100.2019, "N-HEXANE": 86.1754, "ACETONE": 58.0791, "ISOPROPANOL": 60.0952,
    "TOLUENE": 92.1384,
}


def known_mw(project, name: str) -> Optional[float]:
    for s in project.species:
        if s.name == name and s.mw:
            return s.mw
    return BUILTIN_MW.get(name.upper())


def problems(project, reac) -> List[str]:
    """Problems with the ``SPEC_ID_NU`` / ``NU`` stoichiometry of one reaction ([] for simple chemistry)."""
    if not reac.spec_id_nu:
        return []
    out: List[str] = []
    nu = reac.nu or []
    if len(nu) != len(reac.spec_id_nu):
        return [f"{len(reac.spec_id_nu)} species but {len(nu)} stoichiometric coefficients"]
    if not any(v < 0 for v in nu) or not any(v > 0 for v in nu):
        out.append("needs at least one reactant (negative NU) and one product (positive NU)")
    defined = {s.name for s in project.species} | set(BUILTIN_MW)
    for sid in reac.spec_id_nu:
        if sid not in defined and sid.upper() not in defined:
            out.append(f"species {sid!r} is not defined")
    if len(set(reac.spec_id_nu)) != len(reac.spec_id_nu):
        out.append("a species is listed twice")
    if reac.spec_id_n_s and (not reac.n_s or len(reac.n_s) != len(reac.spec_id_n_s)):
        out.append("SPEC_ID_N_S and N_S must have the same length")
    mws = [known_mw(project, sid) for sid in reac.spec_id_nu]
    if all(mws) and not out:
        net = sum(n * m for n, m in zip(nu, mws))
        scale = sum(abs(n) * m for n, m in zip(nu, mws)) / 2
        if scale and abs(net) / scale > 0.01:
            out.append(f"mass is not balanced (net {net:+.2f} g per mole of reaction)")
    return out
