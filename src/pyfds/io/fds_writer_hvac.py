"""FDS writer part: HVAC nodes, ducts, fans, dampers, filters, aircoils, leakages."""
from __future__ import annotations

from typing import Any, Dict

from pyfds.domain.model import Hvac, HvacNode, HvacDuct, Fan, Damper, HvacFilter, HvacLeakage, HvacAircoil

from .fds_writer_common import _nl


class FdsWriterHvacMixin:
    def _write_hvac(self, obj: Hvac) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "DIAMETER": obj.diameter, "LENGTH": obj.length}
        if obj.vent_ids:
            d["VENT_ID"] = obj.vent_ids[0]
        if len(obj.vent_ids) > 1:
            d["VENT_ID2"] = obj.vent_ids[1]
        return _nl("HVAC", d)

    # FDS 6.10 describes the whole network with &HVAC TYPE_ID=...; ducts name their fan, damper and aircoil,
    # nodes name their ducts and filter. The model keeps the reverse links (fan.duct_id ...), so they are
    # turned around here.
    def _ctrl_key(self, ctrl_id: str) -> str:
        return "CTRL_ID" if any(c.name == ctrl_id for c in self._project.controls) else "DEVC_ID"

    def _filter_node(self, flt: HvacFilter):
        """The node a filter sits at: its node_id, else the end of its duct that joins exactly two ducts."""
        if flt.node_id:
            return flt.node_id
        duct = next((x for x in self._project.hvac_ducts if x.name == flt.duct_id), None)
        if duct is None:
            return None
        for n in (duct.node_id_1, duct.node_id_2):
            if sum(n in (x.node_id_1, x.node_id_2) for x in self._project.hvac_ducts) == 2:
                return n
        return None

    def _write_hvac_node(self, obj: HvacNode) -> str:
        p = self._project
        d: Dict[str, Any] = {"TYPE_ID": "NODE", "ID": obj.name}
        ducts = [x.name for x in p.hvac_ducts if obj.name in (x.node_id_1, x.node_id_2)]
        if not ducts and getattr(obj, "duct_id", None):
            ducts = [obj.duct_id]
        if ducts:                              d["DUCT_ID"] = ducts
        if obj.vent_id:                        d["VENT_ID"] = obj.vent_id      # FDS puts the node at the vent centre
        else:                                  d["XYZ"] = [obj.x, obj.y, obj.z]
        if obj.ambient:                        d["AMBIENT"] = True
        flt = next((f for f in p.hvac_filters if self._filter_node(f) == obj.name), None)
        if flt is not None:                    d["FILTER_ID"] = flt.name
        elif getattr(obj, "filter_id", None):  d["FILTER_ID"] = obj.filter_id
        return _nl("HVAC", d)

    def _write_hvac_duct(self, obj: HvacDuct) -> str:
        p = self._project
        d: Dict[str, Any] = {"TYPE_ID": "DUCT", "ID": obj.name, "NODE_ID": [obj.node_id_1, obj.node_id_2]}
        if obj.perimeter is not None:           # non-circular: FDS wants two of area / diameter / perimeter
            d.update({"AREA": obj.area} if obj.area is not None else {"DIAMETER": obj.diameter})
            d.update({"PERIMETER": obj.perimeter, "ROUND": False, "SQUARE": False})
        elif obj.area is not None:
            d["AREA"] = obj.area
        else:
            d["DIAMETER"] = obj.diameter
        if obj.length is not None:             d["LENGTH"] = obj.length
        d["ROUGHNESS"] = obj.roughness
        if tuple(obj.loss) != (0.0, 0.0):      d["LOSS"] = list(obj.loss)
        fan = next((f for f in p.fans if f.duct_id == obj.name), None)
        coil = next((c for c in p.hvac_aircoils if c.duct_id == obj.name), None)
        damper = next((x for x in p.dampers if x.duct_id == obj.name), None)
        ctrl = obj.ctrl_id
        if fan is not None:
            d["FAN_ID"] = fan.name
            ctrl = ctrl or fan.ctrl_id
        elif coil is not None:
            d["AIRCOIL_ID"] = coil.name
            ctrl = ctrl or coil.ctrl_id
        elif damper is not None:
            d["DAMPER"] = True
            ctrl = damper.ctrl_id or ctrl
        if ctrl:                               d[self._ctrl_key(ctrl)] = ctrl
        return _nl("HVAC", d)

    def _write_fan(self, obj: Fan) -> str:
        d: Dict[str, Any] = {"TYPE_ID": "FAN", "ID": obj.name}
        if obj.ramp_id:                        d["RAMP_ID"] = obj.ramp_id
        if obj.volume_flow_rate is not None:   d["VOLUME_FLOW"] = obj.volume_flow_rate
        if obj.max_flow is not None:           d["MAX_FLOW"] = obj.max_flow
        if obj.max_pressure is not None:       d["MAX_PRESSURE"] = obj.max_pressure
        return _nl("HVAC", d)

    def _write_damper(self, obj: Damper) -> str:
        return ""                              # a damper is DAMPER=T plus a control on its duct record

    def _write_hvac_filter(self, obj: HvacFilter) -> str:
        d: Dict[str, Any] = {"TYPE_ID": "FILTER", "ID": obj.name, "EFFICIENCY": obj.efficiency}
        if obj.spec_id:                        d["SPEC_ID"] = obj.spec_id
        if obj.clean_loss is not None:         d["CLEAN_LOSS"] = obj.clean_loss
        if obj.ramp_id:                        d["RAMP_ID"] = obj.ramp_id
        else:                                  d["LOSS"] = obj.loss
        if obj.loading is not None:            d["LOADING"] = obj.loading
        if obj.loading_multiplier is not None: d["LOADING_MULTIPLIER"] = obj.loading_multiplier
        return _nl("HVAC", d)

    def _write_hvac_aircoil(self, obj: HvacAircoil) -> str:
        d: Dict[str, Any] = {"TYPE_ID": "AIRCOIL", "ID": obj.name}
        if obj.fixed_q is not None:
            d["FIXED_Q"] = obj.fixed_q
        else:
            d["EFFICIENCY"] = obj.effectiveness
            if obj.coolant_temperature is not None:   d["COOLANT_TEMPERATURE"] = obj.coolant_temperature
            if obj.coolant_specific_heat is not None: d["COOLANT_SPECIFIC_HEAT"] = obj.coolant_specific_heat
            if obj.coolant_mass_flow is not None:     d["COOLANT_MASS_FLOW"] = obj.coolant_mass_flow
        return _nl("HVAC", d)

    def _write_hvac_leakage(self, obj: HvacLeakage) -> str:
        if not (obj.vent_id and obj.vent2_id):
            return f"! leak path {obj.name} not written: FDS needs VENT_ID and VENT2_ID (it has no pressure zones here)"
        return _nl("HVAC", {"TYPE_ID": "LEAK", "ID": obj.name, "VENT_ID": obj.vent_id,
                            "VENT2_ID": obj.vent2_id, "AREA": obj.area})
