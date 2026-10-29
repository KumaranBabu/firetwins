"""HVAC namelists: HVAC, NODE, DUCT, FAN, DAMPER, FILTER, LEAK.

Mixin for ``FdsParser``: each ``_parse_<tag>`` turns one tokenised record into entities.
"""
from __future__ import annotations

import logging
from typing import Dict
from pyfds.domain.model import FdsProject, Hvac, HvacNode, HvacDuct, Fan, Damper, HvacFilter, HvacLeakage, HvacAircoil

logger = logging.getLogger(__name__)


class HvacBuilders:
    # ``&HVAC TYPE_ID='NODE'|'DUCT'|'FAN'|'FILTER'|'AIRCOIL'|'LEAK'`` is the FDS 6.x form. Fans, filters and
    # aircoils are *classes* that ducts/nodes refer to by id; the model keeps one object per use, so the
    # links are resolved in ``_finish_hvac`` once every record has been read.
    def _hvac_state(self) -> Dict:
        if not hasattr(self, "_hvac_links"):
            self._hvac_links = {"fan": {}, "aircoil": {}, "damper": {}, "filter": {}}
        return self._hvac_links

    def _parse_hvac(self, p: FdsProject, d: Dict) -> None:
        type_id = self._str(d, "TYPE_ID").upper()
        if type_id:
            handler = {"NODE": self._hvac_node, "DUCT": self._hvac_duct, "FAN": self._hvac_fan,
                       "FILTER": self._hvac_filter, "AIRCOIL": self._hvac_aircoil,
                       "LEAK": self._hvac_leak}.get(type_id)
            if handler is None:
                raise ValueError(f"unsupported HVAC TYPE_ID {type_id!r}")
            return handler(p, d)
        name = self._str(d, "ID", f"HVAC_{len(p.hvacs)}")
        vent_ids = [v.strip().strip("'\"") for v in d.get("VENT_ID", "").split(",") if v.strip()]
        p.add_entity(Hvac(name=name, vent_ids=vent_ids,
                          diameter=self._flt(d, "DIAMETER", 0.5),
                          length=self._flt(d, "LENGTH", 1.0)))

    def _hvac_node(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"NODE_{len(p.hvac_nodes)}")
        xyz = [0.0, 0.0, 0.0]
        indexed = [k for k in list(d.keys()) if k.startswith("XYZ(")]
        if indexed:                             # XYZ(3)=0.55 style: only some coordinates given
            for k in range(3):
                v = self._flt(d, f"XYZ({k + 1})")
                if v is not None:
                    xyz[k] = v
            for k in indexed:
                d.get(k)
        elif "XYZ" in d:
            xyz = list(self._parse_xyz(d["XYZ"]))
        d.get("DUCT_ID")                        # derived from the duct records; do not keep as an extra
        fid = self._str(d, "FILTER_ID")
        if fid:
            self._hvac_state()["filter"][name] = fid
        p.add_entity(HvacNode(name=name, x=xyz[0], y=xyz[1], z=xyz[2], vent_id=self._str(d, "VENT_ID") or None,
                              ambient=self._bool(d, "AMBIENT")))

    def _hvac_duct(self, p: FdsProject, d: Dict) -> None:
        name = self._str(d, "ID", f"DUCT_ID_{len(p.hvac_ducts)}")
        nodes = self._strs(d, "NODE_ID") or []
        loss = self._floats(d, "LOSS") or []
        area, diameter = self._flt(d, "AREA"), self._flt(d, "DIAMETER")
        ctrl = self._str(d, "CTRL_ID") or self._str(d, "DEVC_ID") or None
        st = self._hvac_state()
        for key, attr in (("fan", "FAN_ID"), ("aircoil", "AIRCOIL_ID")):
            if self._str(d, attr):
                st[key][name] = self._str(d, attr)
        duct = HvacDuct(name=name, node_id_1=nodes[0] if nodes else "", node_id_2=nodes[1] if len(nodes) > 1 else "",
                        diameter=diameter if diameter is not None else 0.5, area=area,
                        length=self._flt(d, "LENGTH"), perimeter=self._flt(d, "PERIMETER"),
                        roughness=self._flt(d, "ROUGHNESS", 0.0001),
                        loss=(loss[0], loss[1] if len(loss) > 1 else loss[0]) if loss else (0.0, 0.0))
        if self._bool(d, "DAMPER"):
            st["damper"][name] = ctrl
        else:
            duct.ctrl_id = ctrl
        if area is not None and diameter is None and duct.perimeter is None:
            duct.diameter = (4.0 * area / 3.141592653589793) ** 0.5     # shown/edited as a diameter too
        p.add_entity(duct)

    def _hvac_fan(self, p: FdsProject, d: Dict) -> None:
        p.add_entity(Fan(name=self._str(d, "ID", f"FAN_{len(p.fans)}"), duct_id="",
                         ramp_id=self._str(d, "RAMP_ID") or None, volume_flow_rate=self._flt(d, "VOLUME_FLOW"),
                         max_flow=self._flt(d, "MAX_FLOW"), max_pressure=self._flt(d, "MAX_PRESSURE")))

    def _hvac_filter(self, p: FdsProject, d: Dict) -> None:
        eff = self._floats(d, "EFFICIENCY") or [1.0]
        load, mult = self._floats(d, "LOADING"), self._floats(d, "LOADING_MULTIPLIER")
        spec = self._strs(d, "SPEC_ID")
        p.add_entity(HvacFilter(
            name=self._str(d, "ID", f"FILTER_{len(p.hvac_filters)}"), duct_id="", efficiency=eff[0],
            loss=(self._floats(d, "LOSS") or [0.0])[0], clean_loss=self._flt(d, "CLEAN_LOSS"),
            spec_id=spec[0] if spec else None, loading=load[0] if load else None,
            loading_multiplier=mult[0] if mult else None, ramp_id=self._str(d, "RAMP_ID") or None))

    def _hvac_aircoil(self, p: FdsProject, d: Dict) -> None:
        p.add_entity(HvacAircoil(
            name=self._str(d, "ID", f"AIRCOIL_{len(p.hvac_aircoils)}"), duct_id="",
            effectiveness=self._flt(d, "EFFICIENCY", 0.8), fixed_q=self._flt(d, "FIXED_Q"),
            coolant_temperature=self._flt(d, "COOLANT_TEMPERATURE"),
            coolant_specific_heat=self._flt(d, "COOLANT_SPECIFIC_HEAT"),
            coolant_mass_flow=self._flt(d, "COOLANT_MASS_FLOW")))

    def _hvac_leak(self, p: FdsProject, d: Dict) -> None:
        p.add_entity(HvacLeakage(name=self._str(d, "ID", f"LEAK_{len(p.hvac_leakages)}"),
                                 vent_id=self._str(d, "VENT_ID") or None, vent2_id=self._str(d, "VENT2_ID") or None,
                                 area=self._flt(d, "AREA", 0.001)))

    def _finish_hvac(self, p: FdsProject) -> None:
        """Attach the fan/aircoil/filter classes to the ducts and nodes that use them (a class used more than
        once stays one object and lists the further holders in ``more_duct_ids`` / ``more_node_ids``), and turn
        ``DAMPER=T`` into damper objects."""
        st = getattr(self, "_hvac_links", None)
        if not st:
            return
        for key, coll, attr in (("fan", p.fans, "duct_id"), ("aircoil", p.hvac_aircoils, "duct_id"),
                                ("filter", p.hvac_filters, "node_id")):
            for holder, cls_id in st[key].items():
                tmpl = next((x for x in coll if x.name == cls_id), None)
                if tmpl is None:
                    self.warnings.append(f"HVAC: {holder!r} refers to unknown {key} {cls_id!r}")
                    continue
                if not getattr(tmpl, attr):
                    setattr(tmpl, attr, holder)
                else:
                    more = "more_node_ids" if attr == "node_id" else "more_duct_ids"
                    setattr(tmpl, more, [*getattr(tmpl, more), holder])
        for duct, ctrl in st["damper"].items():
            p.add_entity(Damper(name=f"{duct}_damper", duct_id=duct, ctrl_id=ctrl or ""))
        self._hvac_links = {"fan": {}, "aircoil": {}, "damper": {}, "filter": {}}

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
