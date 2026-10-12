"""HVAC namelists: HVAC, NODE, DUCT, FAN, DAMPER, FILTER, LEAK.

Mixin for ``FdsParser``: each ``_parse_<tag>`` turns one tokenised record into entities.
"""
from __future__ import annotations

import logging
from typing import Dict
from pyfds.domain.model import FdsProject, Hvac, HvacNode, HvacDuct, Fan, Damper, HvacFilter, HvacLeakage, HvacAircoil

logger = logging.getLogger(__name__)


class HvacBuilders:
    def _parse_hvac(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"HVAC_{len(p.hvacs)}")
        vent_ids = [v.strip().strip("'\"") for v in d.get("VENT_ID", "").split(",") if v.strip()]
        p.add_entity(Hvac(name=name, vent_ids=vent_ids,
                          diameter=self._flt(d, "DIAMETER", 0.5),
                          length=self._flt(d, "LENGTH", 1.0)))

    def _parse_node(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"NODE_{len(p.hvac_nodes)}")
        xyz_str = d.get("XYZ", "0,0,0")
        xyz = self._parse_xyz(xyz_str)
        p.add_entity(HvacNode(name=name, x=xyz[0], y=xyz[1], z=xyz[2],
                              ambient=self._bool(d, "AMBIENT")))

    def _parse_duct(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"DUCT_{len(p.hvac_ducts)}")
        node_ids = [v.strip().strip("'\"") for v in d.get("NODE_ID", ",").split(",")]
        n1 = node_ids[0] if len(node_ids) > 0 else ""
        n2 = node_ids[1] if len(node_ids) > 1 else ""
        p.add_entity(HvacDuct(name=name, node_id_1=n1, node_id_2=n2,
                              diameter=self._flt(d, "DIAMETER", 0.5),
                              roughness=self._flt(d, "ROUGHNESS", 0.0001)))

    def _parse_fan(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"FAN_{len(p.fans)}")
        p.add_entity(Fan(name=name,
                         duct_id=self._str(d, "DUCT_ID", ""),
                         ramp_id=self._str(d, "RAMP_ID") or None,
                         volume_flow_rate=self._flt(d, "VOLUME_FLOW_RATE")))

    def _parse_damper(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"DAMPER_{len(p.dampers)}")
        p.add_entity(Damper(name=name,
                            duct_id=self._str(d, "DUCT_ID", ""),
                            ctrl_id=self._str(d, "CTRL_ID", "")))

    def _parse_hvac_filter(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"FILTER_{len(p.hvac_filters)}")
        p.add_entity(HvacFilter(
            name=name,
            duct_id=self._str(d, "DUCT_ID", ""),
            efficiency=self._flt(d, "EFFICIENCY", 0.9),
            loss=self._flt(d, "LOSS", 0.0),
            clean_loss=self._flt(d, "CLEAN_LOSS"),
            ctrl_id=self._str(d, "CTRL_ID") or None,
        ))

    def _parse_hvac_leakage(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"LEAK_{len(p.hvac_leakages)}")
        # FDS writes ZONE_ID(1) and ZONE_ID(2) — the parser stores array-indexed
        # keys as "ZONE_ID(1)" / "ZONE_ID(2)"
        zone1 = (self._str(d, "ZONE_ID(1)") or
                 self._str(d, "ZONE_ID") or "")
        zone2 = self._str(d, "ZONE_ID(2)") or ""
        p.add_entity(HvacLeakage(
            name=name,
            zone_id_1=zone1.strip("'\""),
            zone_id_2=zone2.strip("'\""),
            area=self._flt(d, "AREA", 0.001),
            crack_id=self._str(d, "CRACK_ID") or None,
            ctrl_id=self._str(d, "CTRL_ID") or None,
        ))

    def _parse_hvac_aircoil(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"AIRCOIL_{len(p.hvac_aircoils)}")
        p.add_entity(HvacAircoil(
            name=name,
            duct_id=self._str(d, "DUCT_ID", ""),
            effectiveness=self._flt(d, "EFFECTIVENESS", 0.8),
            coolant_temperature=self._flt(d, "COOLANT_TEMPERATURE"),
            coolant_specific_heat=self._flt(d, "COOLANT_SPECIFIC_HEAT"),
            coolant_mass_flow=self._flt(d, "COOLANT_MASS_FLOW"),
            ctrl_id=self._str(d, "CTRL_ID") or None,
        ))
