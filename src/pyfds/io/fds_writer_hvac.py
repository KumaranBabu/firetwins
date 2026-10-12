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

    def _write_hvac_node(self, obj: HvacNode) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "XYZ": [obj.x, obj.y, obj.z]}
        if obj.vent_id:   d["VENT_ID"] = obj.vent_id
        if obj.ambient:   d["AMBIENT"] = obj.ambient
        # P0 fixes
        if getattr(obj, "duct_id", None):   d["DUCT_ID"]   = obj.duct_id
        if getattr(obj, "filter_id", None): d["FILTER_ID"] = obj.filter_id
        return _nl("NODE", d)

    def _write_hvac_duct(self, obj: HvacDuct) -> str:
        d: Dict[str, Any] = {"ID": obj.name,
                             "NODE_ID": [obj.node_id_1, obj.node_id_2],
                             "DIAMETER": obj.diameter,
                             "ROUGHNESS": obj.roughness}
        if obj.length is not None: d["LENGTH"] = obj.length
        if obj.ctrl_id: d["CTRL_ID"] = obj.ctrl_id
        # P0 fixes
        if getattr(obj, "area", None) is not None:       d["AREA"]       = obj.area
        if getattr(obj, "loss", None) is not None:       d["LOSS"]       = list(obj.loss) if isinstance(obj.loss, (list, tuple)) else obj.loss
        if getattr(obj, "perimeter", None) is not None:  d["PERIMETER"]  = obj.perimeter
        if getattr(obj, "leakage_id", None):             d["LEAKAGE_ID"] = obj.leakage_id
        return _nl("DUCT", d)

    def _write_fan(self, obj: Fan) -> str:
        d: Dict[str, Any] = {"ID": obj.name, "DUCT_ID": obj.duct_id}
        if obj.ramp_id:               d["RAMP_ID"]           = obj.ramp_id
        if obj.volume_flow_rate is not None: d["VOLUME_FLOW_RATE"] = obj.volume_flow_rate
        if obj.ctrl_id:               d["CTRL_ID"]           = obj.ctrl_id
        # P0 fixes — fan curve fields
        if getattr(obj, "max_flow", None) is not None:     d["MAX_FLOW"]     = obj.max_flow
        if getattr(obj, "max_pressure", None) is not None: d["MAX_PRESSURE"] = obj.max_pressure
        if getattr(obj, "volume_flow", None):              d["VOLUME_FLOW"]  = obj.volume_flow
        if getattr(obj, "pressure", None):                 d["PRESSURE"]     = obj.pressure
        return _nl("FAN", d)

    def _write_damper(self, obj: Damper) -> str:
        return _nl("DAMPER", {"ID": obj.name, "DUCT_ID": obj.duct_id,
                               "CTRL_ID": obj.ctrl_id})

    def _write_hvac_filter(self, obj: HvacFilter) -> str:
        """Write &FILTER namelist — HVAC particulate filter."""
        d: Dict[str, Any] = {"ID": obj.name, "DUCT_ID": obj.duct_id,
                             "EFFICIENCY": obj.efficiency, "LOSS": obj.loss}
        if obj.clean_loss is not None: d["CLEAN_LOSS"] = obj.clean_loss
        if obj.ctrl_id:                d["CTRL_ID"]    = obj.ctrl_id
        return _nl("FILTER", d)

    def _write_hvac_aircoil(self, obj: HvacAircoil) -> str:
        """Write &AIRCOIL namelist — duct heat exchanger."""
        d: Dict[str, Any] = {"ID": obj.name, "DUCT_ID": obj.duct_id, "EFFECTIVENESS": obj.effectiveness}
        if obj.coolant_temperature is not None:   d["COOLANT_TEMPERATURE"]   = obj.coolant_temperature
        if obj.coolant_specific_heat is not None: d["COOLANT_SPECIFIC_HEAT"] = obj.coolant_specific_heat
        if obj.coolant_mass_flow is not None:     d["COOLANT_MASS_FLOW"]     = obj.coolant_mass_flow
        if obj.ctrl_id:                           d["CTRL_ID"]               = obj.ctrl_id
        return _nl("AIRCOIL", d)

    def _write_hvac_leakage(self, obj: HvacLeakage) -> str:
        """Write &LEAK namelist — duct leakage between pressure zones."""
        d: Dict[str, Any] = {"ID": obj.name,
                             "ZONE_ID(1)": obj.zone_id_1,
                             "ZONE_ID(2)": obj.zone_id_2,
                             "AREA": obj.area}
        if obj.crack_id: d["CRACK_ID"] = obj.crack_id
        if obj.ctrl_id:  d["CTRL_ID"]  = obj.ctrl_id
        return _nl("LEAK", d)
