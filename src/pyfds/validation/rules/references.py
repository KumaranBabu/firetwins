"""Reference-integrity and naming rules (surfaces, ramps, controls, species, duplicates, layers)."""
from __future__ import annotations

from ._common import _e, _w, raw_ids


from typing import Any, Dict, List, Set
from ..engine import ValidationResult, Severity


class DanglingSurfaceRule:
    """Obstructions and vents use surfaces that exist."""
    name = "DanglingSurface"
    _BUILTINS = {"OPEN", "INERT", "MIRROR", "HVAC", "PERIODIC"}

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        surf_ids = {s.name for s in p.surfaces} | self._BUILTINS | raw_ids(p, "SURF")

        # Collect all missing surface IDs in one pass
        missing: Dict[str, str] = {}  # surface_id → referencing entity name

        for v in p.vents:
            if v.surface_id not in surf_ids:
                missing[v.surface_id] = v.name
        for o in p.obstructions:
            if o.surface_id not in surf_ids:
                missing[o.surface_id] = o.name
            if o.surface_ids:
                for sid2 in o.surface_ids:
                    if sid2 and sid2 not in surf_ids:
                        missing[sid2] = o.name

        for missing_id, entity_name in missing.items():
            sid = missing_id

            def _fix(project, _sid=sid):
                from pyfds.domain.model import Surface
                # Only add if still missing (idempotent)
                if not any(s.name == _sid for s in project.surfaces):
                    project.add_entity(Surface(name=_sid, color="GRAY"))

            results.append(ValidationResult(
                severity=Severity.ERROR,
                rule=self.name,
                message=f"Entity '{entity_name}' references undefined surface '{missing_id}'.",
                entity_name=entity_name,
                hint=f"Define &SURF ID='{missing_id}' or use a built-in surface.",
                fix=_fix,
            ))
        return results


class RampMonotonicityRule:
    """Ramp times increase."""
    name = "RampMonotonicity"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for ramp in p.ramps:
            if len(ramp.times) < 2:
                continue
            is_monotonic = all(
                ramp.times[i] > ramp.times[i - 1]
                for i in range(1, len(ramp.times))
            )
            if not is_monotonic:
                ramp_ref = ramp

                def _fix(project, _r=ramp_ref):
                    paired = sorted(zip(_r.times, _r.values))
                    # Remove duplicate times by keeping first occurrence
                    seen: set = set()
                    unique = []
                    for t, f in paired:
                        if t not in seen:
                            seen.add(t)
                            unique.append((t, f))
                    _r.times  = [x[0] for x in unique]
                    _r.values = [x[1] for x in unique]

                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    rule=self.name,
                    message=f"RAMP '{ramp.name}' times are not strictly increasing.",
                    entity_name=ramp.name,
                    hint="FDS requires RAMP T values to be strictly monotonically increasing.",
                    fix=_fix,
                ))
        return results


class ReferenceIntegrityRule:
    """Every ID an entity refers to (surface, ramp, control, device...) exists."""
    name = "ReferenceIntegrity"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        prop_ids  = {pp.name for pp in p.props}     | raw_ids(p, "PROP")
        ctrl_ids  = {c.name  for c in p.controls}   | raw_ids(p, "CTRL")
        ramp_ids  = {r.name  for r in p.ramps}      | raw_ids(p, "RAMP")
        matl_ids  = {m.name  for m in p.materials}  | raw_ids(p, "MATL")
        part_ids  = {pt.name for pt in p.particles} | raw_ids(p, "PART")

        for dev in p.devices:
            if dev.prop_id and dev.prop_id not in prop_ids:
                prop_ids.add(dev.prop_id)
                def _fix_prop(project, _pid=dev.prop_id):
                    from pyfds.domain.model import Prop
                    if not any(pp.name == _pid for pp in project.props):
                        project.add_entity(Prop(name=_pid))
                results.append(ValidationResult(
                    severity=Severity.ERROR, rule=self.name,
                    message=f"DEVC '{dev.name}' PROP_ID='{dev.prop_id}' is undefined.",
                    entity_name=dev.name,
                    hint=f"Define &PROP ID='{dev.prop_id}'.",
                    fix=_fix_prop,
                ))
            if dev.ctrl_id and dev.ctrl_id not in ctrl_ids:
                ctrl_ids.add(dev.ctrl_id)
                results.append(_e(self.name,
                    f"DEVC '{dev.name}' CTRL_ID='{dev.ctrl_id}' is undefined.", entity=dev.name))

        for surf in p.surfaces:
            if surf.ramp_q and surf.ramp_q not in ramp_ids:
                ramp_ids.add(surf.ramp_q)
                def _fix_ramp(project, _rid=surf.ramp_q):
                    from pyfds.domain.model import Ramp
                    if not any(r.name == _rid for r in project.ramps):
                        project.add_entity(Ramp(name=_rid, times=[0.0, 1.0], values=[0.0, 1.0]))
                results.append(ValidationResult(
                    severity=Severity.WARNING, rule=self.name,
                    message=f"SURF '{surf.name}' RAMP_Q='{surf.ramp_q}' is undefined.",
                    entity_name=surf.name,
                    hint=f"Define &RAMP ID='{surf.ramp_q}' with growth data.",
                    fix=_fix_ramp,
                ))
            if surf.matl_id and surf.matl_id not in matl_ids:
                matl_ids.add(surf.matl_id)
                def _fix_matl(project, _mid=surf.matl_id):
                    from pyfds.domain.model import Material
                    if not any(m.name == _mid for m in project.materials):
                        project.add_entity(Material(name=_mid))
                results.append(ValidationResult(
                    severity=Severity.WARNING, rule=self.name,
                    message=f"SURF '{surf.name}' MATL_ID='{surf.matl_id}' is undefined.",
                    entity_name=surf.name,
                    hint=f"Define &MATL ID='{surf.matl_id}'.",
                    fix=_fix_matl,
                ))
            if surf.part_id and surf.part_id not in part_ids:
                results.append(_w(self.name,
                    f"SURF '{surf.name}' PART_ID='{surf.part_id}' is undefined.", entity=surf.name))

        for fan in p.fans:
            if fan.ramp_id and fan.ramp_id not in ramp_ids:
                ramp_ids.add(fan.ramp_id)
                def _fix_fan_ramp(project, _rid=fan.ramp_id):
                    from pyfds.domain.model import Ramp
                    if not any(r.name == _rid for r in project.ramps):
                        project.add_entity(Ramp(name=_rid, times=[0.0, 1.0], values=[0.0, 1.0]))
                results.append(ValidationResult(
                    severity=Severity.WARNING, rule=self.name,
                    message=f"FAN '{fan.name}' RAMP_ID='{fan.ramp_id}' is undefined.",
                    entity_name=fan.name,
                    hint=f"Define &RAMP ID='{fan.ramp_id}'.",
                    fix=_fix_fan_ramp,
                ))

        for ctrl in p.controls:
            if ctrl.input_id and ctrl.input_id not in {d.name for d in p.devices} | raw_ids(p, "DEVC") | ctrl_ids:
                results.append(_w(self.name,
                    f"CTRL '{ctrl.name}' INPUT_ID='{ctrl.input_id}' references no known DEVC or CTRL.",
                    entity=ctrl.name))

        return results


class DuplicateIdRule:
    """IDs are unique within each kind of entity."""
    name = "DuplicateId"

    _COLLECTIONS = [
        "meshes", "obstructions", "holes", "surfaces", "vents", "devices",
        "materials", "reactions", "ramps", "slices", "smoke3ds", "particles", "props",
        "controls", "inits", "hvac_nodes", "hvac_ducts", "fans", "dampers",
        "bndfs", "isofs", "species", "zones", "profs",
        "geoms", "plot3ds", "mesh_transforms",
        "wind_profiles", "moves", "hvac_filters", "hvac_leakages", "hvac_aircoils",
    ]

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for attr in self._COLLECTIONS:
            collection = getattr(p, attr, [])
            seen: Dict[str, int] = {}   # name → first-seen index
            for idx, obj in enumerate(collection):
                n = getattr(obj, "name", None)
                if n is None:
                    continue
                if n in seen:
                    dup_obj = obj

                    def _fix(project, _obj=dup_obj, _attr=attr, _orig=n):
                        col = getattr(project, _attr, [])
                        existing = {getattr(o, "name", None) for o in col if o is not _obj}
                        suffix = 2
                        new_name = f"{_orig}_{suffix}"
                        while new_name in existing:
                            suffix += 1
                            new_name = f"{_orig}_{suffix}"
                        _obj.name = new_name

                    results.append(ValidationResult(
                        severity=Severity.ERROR,
                        rule=self.name,
                        message=f"Duplicate ID '{n}' in '{attr}' collection.",
                        entity_name=n,
                        hint="Each entity of the same type must have a unique ID/name.",
                        fix=_fix,
                    ))
                else:
                    seen[n] = idx
        return results


class SurfaceLayerRule:
    """Surface layers have materials and positive thickness."""
    name = "SurfaceLayer"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for surf in p.surfaces:
            if not surf.layers:
                continue
            total = sum(getattr(lyr, "thickness", 0) or 0 for lyr in surf.layers)
            if total <= 0.0:
                surf_ref = surf

                def _fix(project, _s=surf_ref):
                    default_t = 0.001  # 1 mm default
                    for lyr in _s.layers:
                        if not getattr(lyr, "thickness", None):
                            lyr.thickness = default_t

                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    rule=self.name,
                    message=f"SURF '{surf.name}' has layers defined but total thickness is zero.",
                    entity_name=surf.name,
                    hint="Set a positive THICKNESS for each layer.",
                    fix=_fix,
                ))
        return results


class CtrlLoopRule:
    """Controls do not depend on each other in a loop."""
    name = "CtrlLoop"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        ctrl_names = {c.name for c in p.controls}
        adj: Dict[str, Set[str]] = {}
        for c in p.controls:
            inputs: Set[str] = set()
            ids = c.input_ids if getattr(c, "input_ids", None) else ([c.input_id] if c.input_id else [])
            for iid in ids:
                if iid in ctrl_names:
                    inputs.add(iid)
            adj[c.name] = inputs

        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {n: WHITE for n in ctrl_names}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for nb in adj.get(node, set()):
                if color[nb] == GRAY:
                    return True
                if color[nb] == WHITE and dfs(nb):
                    return True
            color[node] = BLACK
            return False

        for ctrl_name in list(ctrl_names):
            if color[ctrl_name] == WHITE:
                if dfs(ctrl_name):
                    results.append(_e(
                        self.name,
                        f"CTRL '{ctrl_name}' is part of a circular input dependency chain.",
                        entity=ctrl_name,
                        hint="Remove or break the circular CTRL INPUT_ID reference.",
                    ))
        return results


class ControlFunctionRule:
    """CTRL FUNCTION_TYPE must be a known FDS function with the inputs/parameters it needs."""
    name = "ControlFunction"

    def check(self, p: Any) -> List[ValidationResult]:
        from pyfds.domain.control_functions import problems
        return [_w(self.name, f"CTRL '{c.name}': {msg}", entity=c.name,
                   hint="See the FDS User Guide, section 'Control Functions'.")
                for c in p.controls for msg in problems(c)]


class FuelSpeciesRule:
    """Reaction fuels are defined species."""
    name = "FuelSpecies"

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        if not p.reactions:
            return results
        spec_names = {s.name for s in p.species} | raw_ids(p, "SPEC")
        for reac in p.reactions:
            fuel = getattr(reac, "fuel", None)
            if fuel and fuel not in spec_names and not reac.formula:
                spec_names.add(fuel)

                def _fix(project, _fuel=fuel):
                    from pyfds.domain.model import Species
                    if not any(s.name == _fuel for s in project.species):
                        project.add_entity(Species(name=_fuel))

                results.append(ValidationResult(
                    severity=Severity.WARNING,
                    rule=self.name,
                    message=(
                        f"REAC '{reac.name}' FUEL='{fuel}' is not defined as a &SPEC. "
                        f"FDS may not find the correct thermodynamic data."
                    ),
                    entity_name=reac.name,
                    hint=f"Add &SPEC ID='{fuel}' or use FORMULA= to specify the fuel chemistry.",
                    fix=_fix,
                ))
        return results


class BackingValueRule:
    """Surface backing options are consistent."""
    name = "BackingValue"
    _VALID = {"VOID", "INSULATED", "EXPOSED", "AIR"}

    def check(self, p: Any) -> List[ValidationResult]:
        results = []
        for surf in p.surfaces:
            b = getattr(surf, "backing", None)
            if b and b.upper() not in self._VALID:
                surf_ref = surf

                def _fix(project, _s=surf_ref):
                    _s.backing = "VOID"

                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    rule=self.name,
                    message=f"SURF '{surf.name}' BACKING='{b}' is not a valid value.",
                    entity_name=surf.name,
                    hint=f"Valid values: {', '.join(sorted(self._VALID))}.",
                    fix=_fix,
                ))
        return results
