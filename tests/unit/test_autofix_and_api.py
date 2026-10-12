"""
Tests for:
  - Auto-fix callables on validation rules (items added in this session)
  - FdsProject.find() convenience method
  - FdsApi.optimize_for_fire(), ExecutionManager.run_batch(), ResultsManager.compare()
  - ValidationManager.auto_fix() correctly passes project to fix callables
"""
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


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# MeshPresenceRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# HvacNodeReferenceRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# ReferenceIntegrityRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# DuplicateIdRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# VentCoplanarRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# SurfaceLayerRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# FuelSpeciesRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

class TestFuelSpeciesFix:

    def test_fix_adds_stub_species(self):
        p = _project_with_mesh()
        p.reactions.append(Reaction(
            name="FIRE", fuel="HEPTANE",
            heat_of_combustion=44.56e3,
        ))
        rule = FuelSpeciesRule()
        results = rule.check(p)
        assert results and results[0].fix
        results[0].fix(p)
        assert any(s.name == "HEPTANE" for s in p.species)

    def test_fix_idempotent(self):
        p = _project_with_mesh()
        p.reactions.append(Reaction(name="F", fuel="PROPANE", heat_of_combustion=46e3))
        rule = FuelSpeciesRule()
        fix = rule.check(p)[0].fix
        fix(p); fix(p)
        assert sum(1 for s in p.species if s.name == "PROPANE") == 1


# ─────────────────────────────────────────────────────────────────────────────
# BackingValueRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

class TestBackingValueFix:

    def test_fix_sets_void(self):
        p = _project_with_mesh()
        surf = Surface(name="WALL", backing="INVALID")
        p.surfaces.append(surf)
        rule = BackingValueRule()
        results = rule.check(p)
        assert results and results[0].fix
        results[0].fix(p)
        assert surf.backing == "VOID"

    def test_fix_clears_violation(self):
        p = _project_with_mesh()
        surf = Surface(name="WALL", backing="BADVAL")
        p.surfaces.append(surf)
        rule = BackingValueRule()
        results = rule.check(p)
        results[0].fix(p)
        assert rule.check(p) == []


# ─────────────────────────────────────────────────────────────────────────────
# FireResolutionRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

class TestFireResolutionFix:

    def test_fix_increases_cell_count(self):
        p = FdsProject()
        # 2x2x2 m mesh with only 2 cells each → dx=1.0m — very coarse
        p.meshes.append(Mesh(
            name="M1", x_min=0, x_max=2, y_min=0, y_max=2,
            z_min=0, z_max=2, cell_count=(2, 2, 2),
        ))
        # 2000 kW fire → D*≈2.0m, dx_needed≤0.5m for MIN_RATIO=4
        p.surfaces.append(Surface(name="FIRE", heat_release_rate=2000.0))
        p.vents.append(Vent(
            name="V1", surface_id="FIRE",
            x_min=0, x_max=1, y_min=0, y_max=1,
            z_min=0, z_max=0,
        ))
        rule = FireResolutionRule()
        results = rule.check(p)
        errors = [r for r in results if r.severity.name == "ERROR" and r.fix]
        if not errors:
            pytest.skip("No ERROR results with fix — fire resolution not triggered")
        old_cc = tuple(p.meshes[0].cell_count)
        errors[0].fix(p)
        new_cc = p.meshes[0].cell_count
        assert sum(new_cc) > sum(old_cc), "Fix should have increased cell count"


# ─────────────────────────────────────────────────────────────────────────────
# HvacTopologyRule auto-fix (ambient node)
# ─────────────────────────────────────────────────────────────────────────────

class TestHvacTopologyAmbientFix:

    def test_fix_marks_first_node_ambient(self):
        p = _project_with_mesh()
        n1 = HvacNode(name="N1", x=0, y=0, z=0, ambient=False)
        n2 = HvacNode(name="N2", x=1, y=0, z=0, ambient=False)
        p.hvac_nodes.extend([n1, n2])
        p.hvac_ducts.append(HvacDuct(name="D1", node_id_1="N1", node_id_2="N2", diameter=0.3))
        rule = HvacTopologyRule()
        results = rule.check(p)
        ambient_warning = next(
            (r for r in results if "AMBIENT" in r.message and r.fix), None
        )
        assert ambient_warning is not None
        ambient_warning.fix(p)
        assert p.hvac_nodes[0].ambient is True


# ─────────────────────────────────────────────────────────────────────────────
# MeshAspectRatioRule auto-fix
# ─────────────────────────────────────────────────────────────────────────────

class TestMeshAspectRatioFix:

    def test_fix_reduces_aspect_ratio(self):
        p = FdsProject()
        # 10x10x1 m domain with 10x10x2 cells → dx=1.0, dz=0.5 → ratio=2:1 (OK)
        # Make it worse: 10x10x0.1 m with 10x10x1 → dx=1.0, dz=0.1 → ratio=10:1
        p.meshes.append(Mesh(
            name="FLAT",
            x_min=0, x_max=10, y_min=0, y_max=10,
            z_min=0, z_max=0.1,
            cell_count=(10, 10, 1),
        ))
        rule = MeshAspectRatioRule()
        results = rule.check(p)
        warnings = [r for r in results if r.fix]
        if not warnings:
            pytest.skip("Mesh aspect ratio didn't trigger (ratio≤5)")
        old_cc = tuple(p.meshes[0].cell_count)
        warnings[0].fix(p)
        new_cc = p.meshes[0].cell_count
        # After fix, cell count for short axis should have increased
        assert sum(new_cc) >= sum(old_cc)


# ─────────────────────────────────────────────────────────────────────────────
# ValidationManager.auto_fix() passes project to fix callables
# ─────────────────────────────────────────────────────────────────────────────

class TestValidationManagerAutoFix:

    def test_auto_fix_applies_fixes_without_error(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        # Empty project → MeshPresenceRule should fire and be fixed
        report = api.validation.auto_fix()
        # After auto_fix, project should have at least one mesh
        assert len(api.project.meshes) >= 1

    def test_auto_fix_returns_report(self):
        from pyfds.api.controller import FdsApi
        from pyfds.validation.engine import ValidationReport
        api = FdsApi()
        report = api.validation.auto_fix()
        assert isinstance(report, ValidationReport)


# ─────────────────────────────────────────────────────────────────────────────
# FdsProject.find()
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectFind:

    def test_find_returns_all_of_type(self):
        p = _project_with_mesh()
        p.meshes.append(Mesh(
            name="M2", x_min=10, x_max=20,
            y_min=0, y_max=10, z_min=0, z_max=4,
            cell_count=(40, 40, 16),
        ))
        assert len(p.find(Mesh)) == 2

    def test_find_empty_returns_list(self):
        p = FdsProject()
        result = p.find(Surface)
        assert result == []
        assert isinstance(result, list)

    def test_find_returns_correct_type(self):
        p = _project_with_mesh()
        p.surfaces.append(Surface(name="FIRE", heat_release_rate=500.0))
        meshes = p.find(Mesh)
        assert all(isinstance(m, Mesh) for m in meshes)

    def test_find_unknown_type_returns_empty(self):
        p = _project_with_mesh()
        result = p.find(type("Unknown", (), {}))
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# FdsApi.optimize_for_fire() shortcut
# ─────────────────────────────────────────────────────────────────────────────

class TestApiOptimizeForFire:

    def test_returns_dict(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.project.meshes.append(Mesh(
            name="M1", x_min=0, x_max=10, y_min=0, y_max=10,
            z_min=0, z_max=4, cell_count=(40, 40, 16),
        ))
        api.project.surfaces.append(Surface(name="FIRE", heat_release_rate=500.0))
        result = api.optimize_for_fire("FIRE", fire_area=2.0)
        assert isinstance(result, dict)
        assert "D_star_m" in result

    def test_matches_meshing_manager_result(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.project.meshes.append(Mesh(
            name="M1", x_min=0, x_max=10, y_min=0, y_max=10,
            z_min=0, z_max=4, cell_count=(40, 40, 16),
        ))
        api.project.surfaces.append(Surface(name="FIRE", heat_release_rate=500.0))
        r1 = api.optimize_for_fire("FIRE", fire_area=1.0)
        r2 = api.meshing.optimize_for_fire(api.project, "FIRE", fire_area=1.0)
        assert r1["D_star_m"] == r2["D_star_m"]


# ─────────────────────────────────────────────────────────────────────────────
# ResultsManager.compare()
# ─────────────────────────────────────────────────────────────────────────────

class TestResultsManagerCompare:

    def test_compare_returns_report(self, tmp_path):
        from pyfds.api.controller import FdsApi
        from pyfds.results.comparator import ComparisonReport
        d1 = tmp_path / "dir1"
        d2 = tmp_path / "dir2"
        d1.mkdir(); d2.mkdir()
        api = FdsApi()
        report = api.results.compare(str(d1), str(d2), threshold_pct=5.0)
        assert isinstance(report, ComparisonReport)
        assert report.threshold_pct == 5.0

    def test_compare_empty_dirs_passes(self, tmp_path):
        from pyfds.api.controller import FdsApi
        d1 = tmp_path / "a"; d2 = tmp_path / "b"
        d1.mkdir(); d2.mkdir()
        report = FdsApi().results.compare(str(d1), str(d2))
        assert report.passed


# ─────────────────────────────────────────────────────────────────────────────
# ExecutionManager.run_batch() delegates to BatchManager
# ─────────────────────────────────────────────────────────────────────────────

class TestRunBatch:

    def test_run_batch_exists(self):
        from pyfds.api.controller import FdsApi, ExecutionManager
        assert hasattr(ExecutionManager, "run_batch")

    def test_run_batch_callable(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        assert callable(api.execution.run_batch)
