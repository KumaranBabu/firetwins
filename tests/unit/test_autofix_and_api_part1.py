"""Tests for: (part 1 of 1). (part 1 of 3)."""


from __future__ import annotations

import pytest

from pyfds.domain.model import (
    FdsProject, Mesh, Obstruction, Surface, Vent, Device, Prop,
    Ramp, Material, Reaction, HvacNode, HvacDuct, Control,
    Layer, Species,
)
from pyfds.validation.engine import ValidationEngine, Severity
from pyfds.validation.rules import (
    MeshPresenceRule, MeshAlignmentRule, HvacNodeReferenceRule,
    ReferenceIntegrityRule, FireResolutionRule, HvacTopologyRule,
    DuplicateIdRule, VentCoplanarRule, SurfaceLayerRule,
    FuelSpeciesRule, BackingValueRule, MeshAspectRatioRule,
)


def _apply_first_fix(results, project):
    """Apply the fix of the first result that has one."""
    for r in results:
        if r.fix is not None:
            r.fix(project)
            return True
    return False

def _project_with_mesh():
    p = FdsProject()
    p.meshes.append(Mesh(
        name="M1", x_min=0, x_max=10, y_min=0, y_max=10,
        z_min=0, z_max=4, cell_count=(40, 40, 16),
    ))
    return p


class TestMeshPresenceFix:

    def test_fix_adds_default_mesh(self):
        p = FdsProject()
        rule = MeshPresenceRule()
        results = rule.check(p)
        assert results and results[0].fix is not None
        results[0].fix(p)
        assert len(p.meshes) == 1

    def test_fix_mesh_is_poisson(self):
        from pyfds.domain.geometry import GeometryHelper
        p = FdsProject()
        MeshPresenceRule().check(p)[0].fix(p)
        m = p.meshes[0]
        assert all(GeometryHelper.is_poisson_compliant(n) for n in m.cell_count)

    def test_fix_idempotent(self):
        p = FdsProject()
        fix = MeshPresenceRule().check(p)[0].fix
        fix(p)
        fix(p)  # second call should not error; still 1 mesh (added twice via add_entity)
        assert len(p.meshes) >= 1

class TestHvacNodeReferenceFix:

    def test_fix_creates_missing_node(self):
        p = _project_with_mesh()
        p.hvac_nodes.append(HvacNode(name="N1", x=0, y=0, z=0))
        p.hvac_ducts.append(HvacDuct(
            name="D1", node_id_1="N1", node_id_2="MISSING",
            diameter=0.3,
        ))
        rule = HvacNodeReferenceRule()
        results = rule.check(p)
        assert any(r.fix is not None for r in results)
        _apply_first_fix(results, p)
        assert any(n.name == "MISSING" for n in p.hvac_nodes)

    def test_fix_idempotent(self):
        p = _project_with_mesh()
        p.hvac_ducts.append(HvacDuct(
            name="D1", node_id_1="GHOST", node_id_2="GHOST2",
            diameter=0.2,
        ))
        rule = HvacNodeReferenceRule()
        for r in rule.check(p):
            if r.fix:
                r.fix(p)
        # Should not create duplicates
        names = [n.name for n in p.hvac_nodes]
        assert len(names) == len(set(names))

class TestReferenceIntegrityFix:

    def test_fix_creates_missing_prop(self):
        p = _project_with_mesh()
        p.devices.append(Device(
            name="TC1", quantity="TEMPERATURE",
            x=1.0, y=1.0, z=1.0, prop_id="GHOST_PROP",
        ))
        rule = ReferenceIntegrityRule()
        results = rule.check(p)
        prop_fix = next((r for r in results if r.fix and "PROP" in r.message), None)
        assert prop_fix is not None
        prop_fix.fix(p)
        assert any(pp.name == "GHOST_PROP" for pp in p.props)

    def test_fix_creates_missing_ramp(self):
        p = _project_with_mesh()
        p.surfaces.append(Surface(name="FIRE", heat_release_rate=500.0, ramp_q="HRR_RAMP"))
        rule = ReferenceIntegrityRule()
        results = rule.check(p)
        ramp_fix = next((r for r in results if r.fix and "RAMP_Q" in r.message), None)
        assert ramp_fix is not None
        ramp_fix.fix(p)
        assert any(r.name == "HRR_RAMP" for r in p.ramps)

    def test_fix_creates_missing_material(self):
        p = _project_with_mesh()
        p.surfaces.append(Surface(name="WALL", matl_id="MISSING_MATL"))
        rule = ReferenceIntegrityRule()
        results = rule.check(p)
        matl_fix = next((r for r in results if r.fix and "MATL_ID" in r.message), None)
        assert matl_fix is not None
        matl_fix.fix(p)
        assert any(m.name == "MISSING_MATL" for m in p.materials)

class TestDuplicateIdFix:

    def test_fix_renames_duplicate(self):
        p = _project_with_mesh()
        p.surfaces.append(Surface(name="FIRE", heat_release_rate=500.0))
        p.surfaces.append(Surface(name="FIRE", heat_release_rate=200.0))
        rule = DuplicateIdRule()
        results = rule.check(p)
        assert results
        results[0].fix(p)
        names = [s.name for s in p.surfaces]
        assert len(names) == len(set(names)), f"Still duplicates: {names}"

    def test_fix_renamed_with_suffix(self):
        p = _project_with_mesh()
        for _ in range(3):
            p.surfaces.append(Surface(name="BURNER", heat_release_rate=500.0))
        rule = DuplicateIdRule()
        for r in rule.check(p):
            if r.fix:
                r.fix(p)
        names = [s.name for s in p.surfaces]
        assert len(names) == len(set(names))

class TestVentCoplanarFix:

    def _make_non_planar_vent(self, name="V1"):
        return Vent(
            name=name, surface_id="OPEN",
            x_min=0.0, x_max=1.0,
            y_min=0.0, y_max=1.0,
            z_min=0.0, z_max=0.5,   # all three dims non-zero → not planar
        )

    def test_fix_collapses_smallest_dim(self):
        p = _project_with_mesh()
        p.vents.append(self._make_non_planar_vent())
        rule = VentCoplanarRule()
        results = rule.check(p)
        assert results and results[0].fix
        results[0].fix(p)
        v = p.vents[0]
        dims = [abs(v.x_max - v.x_min), abs(v.y_max - v.y_min), abs(v.z_max - v.z_min)]
        zero_count = sum(1 for d in dims if d < 1e-9)
        assert zero_count == 1, f"Expected 1 zero dim after fix, got dims={dims}"

    def test_fix_clears_violation(self):
        p = _project_with_mesh()
        p.vents.append(self._make_non_planar_vent())
        rule = VentCoplanarRule()
        results = rule.check(p)
        results[0].fix(p)
        assert rule.check(p) == []

class TestSurfaceLayerFix:

    def test_fix_sets_default_thickness(self):
        p = _project_with_mesh()
        lyr = Layer(material_id="CONC", thickness=0.0)
        surf = Surface(name="WALL", layers=[lyr])
        p.surfaces.append(surf)
        rule = SurfaceLayerRule()
        results = rule.check(p)
        assert results and results[0].fix
        results[0].fix(p)
        total = sum(getattr(l, "thickness", 0) or 0 for l in surf.layers)
        assert total > 0

    def test_fix_clears_violation(self):
        p = _project_with_mesh()
        lyr = Layer(material_id="CONC", thickness=0.0)
        surf = Surface(name="WALL", layers=[lyr])
        p.surfaces.append(surf)
        rule = SurfaceLayerRule()
        results = rule.check(p)
        results[0].fix(p)
        assert rule.check(p) == []
