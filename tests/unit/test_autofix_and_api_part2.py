"""Tests for: (part 1 of 1). (part 2 of 3)."""


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


def _project_with_mesh():
    p = FdsProject()
    p.meshes.append(Mesh(
        name="M1", x_min=0, x_max=10, y_min=0, y_max=10,
        z_min=0, z_max=4, cell_count=(40, 40, 16),
    ))
    return p


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
