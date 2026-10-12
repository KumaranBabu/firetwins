"""Rules for surfaces, materials and reactions (SRF-01, MAT-03, RXN-01)."""
from __future__ import annotations

from typing import Any, List

from ._common import _e, _w
from ..engine import ValidationResult


class SurfaceTypeRule:
    """Surfaces mix no contradictory behaviours (two flow specs, burner + fixed temperature, bad leak path)."""
    name = "SurfaceType"

    def check(self, p: Any) -> List[ValidationResult]:
        from pyfds.domain.surface_types import problems
        return [_w(self.name, f"SURF '{s.name}': {msg}", entity=s.name,
                   hint="Pick one surface type: burner, supply/exhaust, heater/cooler, layered or air leak.")
                for s in p.surfaces for msg in problems(s)]


class LiquidFuelRule:
    """A liquid-fuel material (boiling temperature set) has a heat of vaporisation and a fuel species."""
    name = "LiquidFuel"

    def check(self, p: Any) -> List[ValidationResult]:
        from pyfds.domain.reaction_checks import BUILTIN_MW
        out = []
        known = {s.name for s in p.species}
        for m in p.materials:
            if m.boiling_temperature is None:
                continue
            if m.heat_of_reaction is None:
                out.append(_e(self.name, f"MATL '{m.name}': liquid fuel without a heat of vaporisation (HEAT_OF_REACTION)", m.name))
            if not m.spec_ids:
                out.append(_e(self.name, f"MATL '{m.name}': liquid fuel without a fuel species (SPEC_ID)", m.name))
            else:
                for sid in m.spec_ids:
                    if sid not in known and sid.upper() not in BUILTIN_MW:
                        out.append(_w(self.name, f"MATL '{m.name}': fuel species '{sid}' is not defined", m.name))
        return out


class ComplexReactionRule:
    """Reactions given species by species have matching, mass-balanced stoichiometry."""
    name = "ComplexReaction"

    def check(self, p: Any) -> List[ValidationResult]:
        from pyfds.domain.reaction_checks import problems
        return [_w(self.name, f"REAC '{r.name}': {msg}", entity=r.name,
                   hint="List SPEC_ID_NU and NU in the same order; reactants negative, products positive.")
                for r in p.reactions for msg in problems(p, r)]
