"""Species (&SPEC) and pressure zones (&ZONE) — authoring API.

Before G3 these entities could be imported/exported but not created or edited
through the API, the agent or the GUI.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

from .base import _CollectionManager


def _unique(manager: _CollectionManager, base: str) -> str:
    """``base``, or ``base_2``, ``base_3``… — the first name not yet used."""
    if manager.get(base) is None:
        return base
    i = 2
    while manager.get(f"{base}_{i}") is not None:
        i += 1
    return f"{base}_{i}"


class SpeciesManager(_CollectionManager):
    """Gas species: ``api.species``."""

    def __init__(self, api) -> None:
        from pyfds.domain.model import Species
        super().__init__(api, Species)

    def add_species(self, name: str, mw: Optional[float] = None, **fields) -> Any:
        """Add a primitive species. Name must be unique."""
        from pyfds.domain.model import Species
        if self.get(name) is not None:
            raise ValueError(f"species {name!r} already exists")
        spec = Species(name=name, mw=mw, **fields)
        self.add(spec)
        return spec

    def add_lumped(self, name: str, components: Sequence[str],
                   volume_fractions: Optional[Sequence[float]] = None,
                   mass_fractions: Optional[Sequence[float]] = None, **fields) -> Any:
        """Add a lumped (mixture) species built from existing component species."""
        from pyfds.domain.model import Species
        if self.get(name) is not None:
            raise ValueError(f"species {name!r} already exists")
        if volume_fractions is not None and mass_fractions is not None:
            raise ValueError("give volume_fractions or mass_fractions, not both")
        fractions = volume_fractions if volume_fractions is not None else mass_fractions
        if fractions is None or len(fractions) != len(components):
            raise ValueError("fractions must be given, one per component")
        missing = [c for c in components if self.get(c) is None]
        if missing:
            raise ValueError(f"unknown component species: {', '.join(missing)}")
        spec = Species(
            name=name, primitive=False, spec_id=list(components),
            volume_fraction=list(volume_fractions) if volume_fractions is not None else None,
            mass_fraction=list(mass_fractions) if mass_fractions is not None else None,
            **fields)
        self.add(spec)
        return spec

    def set_background(self, name: str) -> Any:
        """Make *name* the background species (clears the flag on all others), one undo step."""
        from pyfds.automation.commands import GroupCommand, ModifyPropertyCommand
        target = self.get(name)
        if target is None:
            raise KeyError(f"{name!r} not found")
        cmds = [ModifyPropertyCommand(s, "background", s is target) for s in self.all()
                if s.background != (s is target)]
        if cmds:
            res = self._pipe.execute(GroupCommand(cmds, label=f"background species = {name}"))
            if not res.success:
                raise ValueError(res.message)
        return target

    def users_of(self, name: str) -> List[str]:
        """Entities that reference species *name* (lumped species, reactions)."""
        users: List[str] = []
        for sp in self.all():
            if name in (sp.spec_id or []) and sp.name != name:
                users.append(f"SPEC {sp.name}")
        for r in self._project.reactions:
            if name in {getattr(r, "fuel", None), getattr(r, "spec_id", None)}:
                users.append(f"REAC {getattr(r, 'name', '')}")
        return users

    def remove_checked(self, name: str) -> None:
        """Remove a species unless something still references it."""
        users = self.users_of(name)
        if users:
            raise ValueError(f"species {name!r} is used by: {', '.join(users)}")
        entity = self.get(name)
        if entity is None:
            raise KeyError(f"{name!r} not found")
        self.remove(entity)


class ZoneManager(_CollectionManager):
    """Pressure zones: ``api.zones``."""

    def __init__(self, api) -> None:
        from pyfds.domain.model import Zone
        super().__init__(api, Zone)

    def add_zone(self, xyz: Sequence[float], name: Optional[str] = None, **fields) -> Any:
        """Add a pressure zone identified by one interior point (FDS ``XYZ=``)."""
        from pyfds.domain.model import Zone
        if len(xyz) != 3:
            raise ValueError("xyz must be [x, y, z]")
        if name and self.get(name) is not None:
            raise ValueError(f"zone {name!r} already exists")
        zone = Zone(name=name or _unique(self, "ZONE"),
                    xyz=tuple(float(v) for v in xyz), **fields)
        self.add(zone)
        return zone

    def set_leak_areas(self, zone, leak_areas: Sequence[float]) -> Any:
        return self.update(zone, leak_areas=[float(a) for a in leak_areas])
