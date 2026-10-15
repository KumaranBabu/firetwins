"""Pyrolysis kinetics and by-products on materials (B4). A mixin for ``MaterialManager``."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from pyfds.domain import pyrolysis_kinetics as pk


class MaterialTools:
    """Mixin for ``MaterialManager`` (needs ``get``, ``_api``)."""

    def _material(self, material):
        m = self.get(material) if isinstance(material, str) else material
        if m is None:
            raise KeyError(f"material {material!r} not found")
        return m

    def fit_pyrolysis(self, material, temperature_c: Sequence[float], rate: Sequence[float], n: float = 1.0,
                      remaining_mass: Optional[Sequence[float]] = None, apply: bool = True) -> Dict[str, Any]:
        """Work out A (1/s) and E (J/mol) from a reaction-rate curve ``rate(T)`` and, with *apply*, set them
        on the material together with the reaction order *n* (one undo step). With *remaining_mass* the rate
        is first divided by ``Y^n``. Returns the fit (``A``, ``E``, ``r2``, ``points``)."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        m = self._material(material)
        fit = pk.fit_arrhenius(temperature_c, rate, n=n, remaining_mass=remaining_mass)
        if apply:
            self._api.history.execute(GroupCommand([
                ModifyPropertyCommand(m, "a", fit["A"]), ModifyPropertyCommand(m, "e", fit["E"]),
                ModifyPropertyCommand(m, "n_s", float(n))], label=f"fit pyrolysis of {m.name}"))
        return fit

    def pyrolysis_from_peak(self, material, heating_rate_k_per_min: float, peak_temperature_c: float,
                            activation_energy: Optional[float] = None, other_runs: Optional[Sequence[Sequence[float]]] = None,
                            n: float = 1.0, apply: bool = True) -> Dict[str, float]:
        """A and E from a TGA peak (Kissinger). Give *activation_energy* (J/mol), or *other_runs* as
        ``[(heating rate K/min, peak deg C), ...]`` so E is fitted from all runs including this one."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        m = self._material(material)
        if activation_energy is None:
            if not other_runs:
                raise ValueError("give activation_energy, or other_runs (at least one more heating rate)")
            runs = [(heating_rate_k_per_min, peak_temperature_c), *[tuple(r) for r in other_runs]]
            activation_energy = pk.kissinger_activation_energy([r[0] for r in runs], [r[1] for r in runs])
        res = pk.from_peak(heating_rate_k_per_min, peak_temperature_c, activation_energy, n)
        if apply:
            self._api.history.execute(GroupCommand([
                ModifyPropertyCommand(m, "a", res["A"]), ModifyPropertyCommand(m, "e", res["E"]),
                ModifyPropertyCommand(m, "n_s", float(n))], label=f"pyrolysis of {m.name} from TGA peak"))
        return res

    def byproducts(self, material) -> Dict[str, Any]:
        """The gases (species -> mass yield) and residue a material gives off when it reacts."""
        m = self._material(material)
        return {"gases": dict(zip(m.spec_ids or [], m.nu_gases or [])), "residue": m.nu_residue or 0.0,
                "residue_material": m.residue_id}

    def set_byproducts(self, material, gases: Dict[str, float], residue: float = 0.0,
                       residue_material: Optional[str] = None) -> Dict[str, Any]:
        """Set what reacting material turns into: *gases* ``{species: mass yield}`` plus a solid *residue*
        yield; the yields are fractions of the reacted mass and must not add up to more than 1. FDS needs the
        residue to be a material, so give *residue_material* (an existing material) whenever there is a residue.
        A shortfall is reported (``unaccounted``), not hidden. One undo step."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        m = self._material(material)
        if any(v < 0 for v in gases.values()) or residue < 0:
            raise ValueError("yields cannot be negative")
        if residue_material is not None and self.get(residue_material) is None:
            raise KeyError(f"residue material {residue_material!r} not found")
        if residue_material is not None and residue_material == m.name:
            raise ValueError("a material cannot be its own residue")
        total = sum(gases.values()) + residue
        if total > 1.0 + 1e-6:
            raise ValueError(f"yields add up to {total:.3f}; they cannot exceed 1")
        self._api.history.execute(GroupCommand([
            ModifyPropertyCommand(m, "spec_ids", list(gases) or None),
            ModifyPropertyCommand(m, "nu_gases", [float(v) for v in gases.values()] or None),
            ModifyPropertyCommand(m, "nu_residue", float(residue) if residue else None),
            ModifyPropertyCommand(m, "residue_id", residue_material or None)],
            label=f"by-products of {m.name}"))
        return {"gases": dict(gases), "residue": residue, "residue_material": residue_material,
                "unaccounted": max(0.0, 1.0 - total)}
