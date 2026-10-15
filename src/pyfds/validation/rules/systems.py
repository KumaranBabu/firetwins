"""Rules for device systems, HVAC layout and particle classes (B4)."""
from __future__ import annotations

from typing import Any, List

from ._common import _e, _w
from ..engine import ValidationResult

_HVAC_PREFIXES = ("DUCT ", "NODE ", "FAN ", "AIRCOIL ", "FILTER ")


class DeviceSystemRule:
    """Aspiration samplers feed an ASPIRATION detector; beams have a length; HVAC outputs name existing ducts
    and nodes; nozzles can spray; FED activity is 1-3."""
    name = "DeviceSystem"

    def check(self, p: Any) -> List[ValidationResult]:
        out: List[ValidationResult] = []
        devs = {d.name: d for d in p.devices}
        props = {x.name: x for x in p.props}
        ducts, nodes = {d.name for d in p.hvac_ducts}, {n.name for n in p.hvac_nodes}
        for d in p.devices:
            q = d.quantity
            if d.devc_id:
                target = devs.get(d.devc_id)
                if target is None or target.quantity != "ASPIRATION":
                    out.append(_e(self.name, f"DEVC '{d.name}': DEVC_ID '{d.devc_id}' is not an ASPIRATION device", d.name))
                if not d.flowrate or d.flowrate <= 0:
                    out.append(_e(self.name, f"DEVC '{d.name}': an aspiration sampling point needs a positive FLOWRATE", d.name))
            if q == "ASPIRATION" and not any(s.devc_id == d.name for s in p.devices):
                out.append(_w(self.name, f"DEVC '{d.name}': aspiration detector with no sampling points", d.name,
                              hint="Give sampling devices DEVC_ID, FLOWRATE and DELAY."))
            if q in ("PATH OBSCURATION", "TRANSMISSION"):
                if d.xb is None:
                    out.append(_e(self.name, f"DEVC '{d.name}': a beam detector needs XB (the beam line)", d.name))
                elif all(abs(a - b) < 1e-9 for a, b in zip(d.xb[0::2], d.xb[1::2])):
                    out.append(_e(self.name, f"DEVC '{d.name}': the beam has zero length", d.name))
            if q.startswith(_HVAC_PREFIXES):
                if q.startswith(("DUCT ", "FAN ", "AIRCOIL ")) and d.duct_id not in ducts:
                    out.append(_e(self.name, f"DEVC '{d.name}': {q} needs an existing DUCT_ID (got {d.duct_id!r})", d.name))
                if q.startswith(("NODE ", "FILTER ")):
                    want = 2 if q == "NODE PRESSURE DIFFERENCE" else 1
                    ids = d.node_id or []
                    if len(ids) != want or any(i not in nodes for i in ids):
                        out.append(_e(self.name, f"DEVC '{d.name}': {q} needs {want} existing NODE_ID value(s)", d.name))
                if ("FRACTION" in q or "LOADING" in q) and not d.spec_id:
                    out.append(_e(self.name, f"DEVC '{d.name}': {q} needs SPEC_ID", d.name))
            prop = props.get(d.prop_id) if d.prop_id else None
            if prop is not None and q == "CONTROL" and not prop.part_id:
                out.append(_w(self.name, f"DEVC '{d.name}': property '{prop.name}' has no PART_ID, so nothing sprays", d.name))
        for pr in p.props:
            if pr.fed_activity is not None and pr.fed_activity not in (1, 2, 3):
                out.append(_e(self.name, f"PROP '{pr.name}': FED_ACTIVITY must be 1, 2 or 3", pr.name))
        return out


class HvacLayoutRule:
    """FDS limits on a duct network: one fan/damper/aircoil per duct, a fan defined one way, filters at
    two-duct nodes, terminal nodes with one duct, leak paths between two vents."""
    name = "HvacLayout"

    def check(self, p: Any) -> List[ValidationResult]:
        out: List[ValidationResult] = []
        count = {}
        for d in p.hvac_ducts:
            for n in (d.node_id_1, d.node_id_2):
                count[n] = count.get(n, 0) + 1
            kinds = [k for k, coll in (("fan", p.fans), ("damper", p.dampers), ("aircoil", p.hvac_aircoils))
                     if any(x.duct_id == d.name for x in coll)]
            if len(kinds) > 1:
                out.append(_e(self.name, f"duct '{d.name}' has {' and '.join(kinds)}; FDS allows only one of them per duct", d.name))
        for f in p.fans:
            ways = sum(v is not None for v in (f.volume_flow_rate, f.ramp_id)) + (f.max_flow is not None or f.max_pressure is not None)
            if ways > 1:
                out.append(_e(self.name, f"fan '{f.name}' is defined more than one way (VOLUME_FLOW, MAX_FLOW + MAX_PRESSURE, RAMP_ID)", f.name))
            if (f.max_flow is None) != (f.max_pressure is None):
                out.append(_e(self.name, f"fan '{f.name}': a quadratic fan needs both MAX_FLOW and MAX_PRESSURE", f.name))
        for n in p.hvac_nodes:
            if (n.ambient or n.vent_id) and count.get(n.name, 0) != 1:
                out.append(_e(self.name, f"node '{n.name}' is a terminal (ambient or at a vent) so it needs exactly one duct, has {count.get(n.name, 0)}", n.name))
        for flt in p.hvac_filters:
            node = flt.node_id
            if node and count.get(node, 0) != 2:
                out.append(_e(self.name, f"filter '{flt.name}' sits at node '{node}' which has {count.get(node, 0)} duct(s); it needs exactly 2", flt.name))
            node_obj = next((n for n in p.hvac_nodes if n.name == node), None)
            if node_obj is not None and (node_obj.ambient or node_obj.vent_id):
                out.append(_e(self.name, f"filter '{flt.name}' cannot be at an ambient or vent node", flt.name))
        tracked = {s.name for s in p.species if not s.lumped_component_only}
        for flt in p.hvac_filters:
            if flt.spec_id and flt.spec_id not in tracked:
                out.append(_e(self.name, f"filter '{flt.name}' removes species '{flt.spec_id}', which is not a tracked "
                              "species of this model", flt.name,
                              hint="Define it with its own SPEC line (not LUMPED_COMPONENT_ONLY), e.g. PARTICULATE."))
        for lk in p.hvac_leakages:
            if not (lk.vent_id and lk.vent2_id):
                out.append(_w(self.name, f"leak path '{lk.name}' has no VENT_ID/VENT2_ID, so it is not written to the FDS file", lk.name))
        return out


class ParticleKindRule:
    """Massless tracers carry no species or surface; target-only particles need a surface."""
    name = "ParticleKind"

    def check(self, p: Any) -> List[ValidationResult]:
        out: List[ValidationResult] = []
        for x in p.particles:
            if x.massless and (x.spec_id or x.surf_id):
                out.append(_e(self.name, f"PART '{x.name}': massless particles cannot have a SPEC_ID or SURF_ID", x.name))
            if x.target_only and not x.surf_id:
                out.append(_e(self.name, f"PART '{x.name}': TARGET_ONLY needs a SURF_ID", x.name))
        return out


class MaterialResidueRule:
    """FDS has no residue yield on its own: it needs the residue to be a material (NU_MATL with MATL_ID)."""
    name = "MaterialResidue"

    def check(self, p: Any) -> List[ValidationResult]:
        out: List[ValidationResult] = []
        names = {m.name for m in p.materials}
        for m in p.materials:
            if m.residue_id and m.residue_id not in names:
                out.append(_e(self.name, f"MATL '{m.name}': residue material '{m.residue_id}' is not defined", m.name))
            elif m.nu_residue and not m.residue_id:
                out.append(_w(self.name, f"MATL '{m.name}': a residue yield of {m.nu_residue:g} is not written "
                                         "because no residue material is chosen", m.name,
                              hint="Choose the residue material on the Byproducts tab of Edit Materials."))
            if m.residue_id and m.nu_residue and m.nu_residue + sum(m.nu_gases or []) > 1.0 + 1e-9:
                out.append(_e(self.name, f"MATL '{m.name}': residue and gas yields add up to more than 1", m.name))
        return out
