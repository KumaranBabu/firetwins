"""Egress (Pathfinder-style) coupling: the FDS outputs an evacuation tool reads, and a scenario export
(TH-08). Accessible via ``api.egress``.

Pathfinder, STEPS and similar tools read FDS results (slice files, Plot3D, devices); they need hazard fields at
head height and the exit layout. This manager adds those outputs to the model and describes the scenario in
the solver-neutral :class:`~pyfds.domain.egress.EgressScenario`.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from pyfds.domain.egress import EgressScenario, ExitZone, OccupantGroup

if TYPE_CHECKING:
    from .facade import FdsApi

#: (quantity, species) pairs for the head-height hazard slices
HAZARD_SLICES = (("TEMPERATURE", None), ("VISIBILITY", None), ("VOLUME FRACTION", "CARBON MONOXIDE"),
                 ("VOLUME FRACTION", "CARBON DIOXIDE"), ("VOLUME FRACTION", "OXYGEN"))


class EgressManager:
    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    def exits(self) -> List[ExitZone]:
        """Exit candidates from the model: every vent that opens to the outside (surface ``OPEN``) and every
        hole, as exit zones named after the entity."""
        p = self._api.project
        out = [ExitZone(id=v.name, xb=(v.x_min, v.x_max, v.y_min, v.y_max, v.z_min, v.z_max))
               for v in p.vents if v.surface_id == "OPEN"]
        out += [ExitZone(id=h.name, xb=(h.x_min, h.x_max, h.y_min, h.y_max, h.z_min, h.z_max)) for h in p.holes]
        return out

    def add_outputs(self, height: float = 1.8, quantities: Optional[Sequence] = None) -> List[Any]:
        """Add head-height slices (default 1.8 m): temperature, visibility, CO, CO2 and O2 volume fractions
        (one undo step). Slices that already exist at that height are not duplicated."""
        p = self._api.project
        if not p.meshes:
            raise ValueError("add a mesh first")
        if not any(m.z_min <= height <= m.z_max for m in p.meshes):
            raise ValueError(f"height {height} m is outside every mesh")
        made = []
        with self._api.history.transaction(f"add egress outputs at {height} m"):
            for qty, spec in (quantities or HAZARD_SLICES):
                if any(s.quantity == qty and s.plane.upper() == "Z" and abs(s.position - height) < 1e-9
                       and getattr(s, "spec_id", None) == spec for s in p.slices):
                    continue
                kw = {"spec_id": spec} if spec else {}
                made.append(self._api.slices.add_slice(qty, "Z", height, **kw))
        return made

    def scenario(self, t_start_evac: float = 0.0, groups: Sequence[Dict[str, Any]] = (),
                 tenability_limits: Optional[Dict[str, float]] = None) -> EgressScenario:
        """An :class:`EgressScenario` for this project: its exits, the given occupant *groups*
        (``{"id", "count", "start_region": [6 numbers]}``), the project's device names as hazard channels
        and the tenability limits (default: ``api.tenability`` style 60 deg C, 1400 ppm CO)."""
        p = self._api.project
        occupants = [OccupantGroup(id=g["id"], count=int(g["count"]), start_region=tuple(g["start_region"]))
                     for g in groups]
        return EgressScenario(
            fds_chid=p.chid, t_start_evac=t_start_evac, exits=self.exits(), occupant_groups=occupants,
            hazard_channels=[d.name for d in p.devices],
            tenability_limits=dict(tenability_limits or {"TEMPERATURE": 60.0, "CO_PPM": 1400.0}))

    def export(self, path: str, **scenario_args) -> Dict[str, Any]:
        """Write the scenario as JSON for the egress tool; returns the dict."""
        data = self.scenario(**scenario_args).to_dict()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return data
