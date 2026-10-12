"""Unit tests for the PyFDS gap-fill additions: (part 1 of 4)."""


from __future__ import annotations

import pytest
from pyfds.io.fds_writer import FdsWriter
from pyfds.domain.model import (
    FdsProject, Mesh, Surface, Vent, Device, Particle, Prop, Species,
    Material, MaterialReaction, Reaction, HvacNode, HvacDuct, Fan,
    Control, Init, Slice, Layer,
    WindProfile, Move, HvacFilter, HvacLeakage,
)
from pyfds.validation.engine import ValidationEngine, Severity
from pyfds.validation.rules import (
    DuplicateIdRule, VentCoplanarRule, DeviceBoundsRule,
    SurfaceLayerRule, CtrlLoopRule, FuelSpeciesRule,
    BackingValueRule, MeshAspectRatioRule, InitBoundsRule,
    SliceBoundsRule,
)


def _mesh(name="m1", nx=20, ny=20, nz=10,
          x0=0, x1=4, y0=0, y1=4, z0=0, z1=2):
    return Mesh(name=name, cell_count=(nx, ny, nz),
                x_min=x0, x_max=x1, y_min=y0, y_max=y1, z_min=z0, z_max=z1)

def _project_with_mesh(**kw):
    p = FdsProject()
    p.add_entity(_mesh(**kw))
    return p


class TestDuplicateIdRule:
    rule = DuplicateIdRule()

    def test_no_duplicates_passes(self):
        p = _project_with_mesh()
        p.add_entity(Surface(name="fire"))
        p.add_entity(Surface(name="inert"))
        results = self.rule.check(p)
        assert results == []

    def test_duplicate_surface_id_is_error(self):
        p = FdsProject()
        p.surfaces.append(Surface(name="dup"))
        p.surfaces.append(Surface(name="dup"))
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) >= 1
        assert "dup" in errors[0].message

    def test_duplicate_mesh_id_is_error(self):
        p = FdsProject()
        p.meshes.append(_mesh("same"))
        p.meshes.append(_mesh("same"))
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) >= 1

    def test_same_name_in_different_collections_passes(self):
        p = FdsProject()
        p.add_entity(Surface(name="fire"))
        p.add_entity(Device(name="fire", x=1, y=1, z=1))
        results = self.rule.check(p)
        assert results == []

    def test_empty_project_passes(self):
        results = self.rule.check(FdsProject())
        assert results == []

    def test_rule_name(self):
        assert self.rule.name == "DuplicateId"

class TestVentCoplanarRule:
    rule = VentCoplanarRule()

    def test_z_planar_vent_passes(self):
        p = FdsProject()
        p.add_entity(Vent(name="top", x_min=0, x_max=4, y_min=0, y_max=4,
                          z_min=2, z_max=2, surface_id="OPEN"))
        results = self.rule.check(p)
        assert results == []

    def test_x_planar_vent_passes(self):
        p = FdsProject()
        p.add_entity(Vent(name="side", x_min=1, x_max=1, y_min=0, y_max=4,
                          z_min=0, z_max=2, surface_id="OPEN"))
        results = self.rule.check(p)
        assert results == []

    def test_volumetric_vent_is_error(self):
        p = FdsProject()
        p.add_entity(Vent(name="vol", x_min=0, x_max=1, y_min=0, y_max=1,
                          z_min=0, z_max=1, surface_id="OPEN"))
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "vol" in errors[0].message

    def test_line_vent_two_zero_dims_is_error(self):
        p = FdsProject()
        p.add_entity(Vent(name="line", x_min=0, x_max=4, y_min=1, y_max=1,
                          z_min=0.5, z_max=0.5, surface_id="OPEN"))
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) == 1

    def test_empty_project_passes(self):
        assert self.rule.check(FdsProject()) == []

class TestDeviceBoundsRule:
    rule = DeviceBoundsRule()

    def test_device_inside_mesh_passes(self):
        p = _project_with_mesh()
        p.add_entity(Device(name="tc", x=2, y=2, z=1, quantity="TEMPERATURE"))
        results = self.rule.check(p)
        assert results == []

    def test_device_outside_all_meshes_is_warning(self):
        p = _project_with_mesh(x0=0, x1=4, y0=0, y1=4, z0=0, z1=2)
        p.add_entity(Device(name="far", x=10, y=10, z=10, quantity="TEMPERATURE"))
        results = self.rule.check(p)
        warnings = [r for r in results if r.severity == Severity.WARNING]
        assert len(warnings) == 1
        assert "far" in warnings[0].message

    def test_device_on_mesh_boundary_passes(self):
        p = _project_with_mesh(x0=0, x1=4, y0=0, y1=4, z0=0, z1=2)
        p.add_entity(Device(name="edge", x=4, y=4, z=2, quantity="TEMPERATURE"))
        results = self.rule.check(p)
        assert results == []

    def test_no_meshes_skips_check(self):
        p = FdsProject()
        p.add_entity(Device(name="d", x=100, y=100, z=100, quantity="TEMPERATURE"))
        results = self.rule.check(p)
        assert results == []

class TestSurfaceLayerRule:
    rule = SurfaceLayerRule()

    def test_surface_no_layers_passes(self):
        p = FdsProject()
        p.add_entity(Surface(name="plain"))
        results = self.rule.check(p)
        assert results == []

    def test_surface_with_positive_thickness_passes(self):
        p = FdsProject()
        surf = Surface(name="wall")
        surf.layers = [Layer(material_id="WOOD", thickness=0.02)]
        p.add_entity(surf)
        results = self.rule.check(p)
        assert results == []

    def test_surface_with_zero_thickness_is_error(self):
        p = FdsProject()
        surf = Surface(name="bad_wall")
        surf.layers = [Layer(material_id="WOOD", thickness=0.0)]
        p.add_entity(surf)
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "bad_wall" in errors[0].message

    def test_multiple_layers_sum_to_zero_is_error(self):
        p = FdsProject()
        surf = Surface(name="multilayer")
        surf.layers = [
            Layer(material_id="STEEL", thickness=0.0),
            Layer(material_id="INSUL", thickness=0.0),
        ]
        p.add_entity(surf)
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) == 1

class TestCtrlLoopRule:
    rule = CtrlLoopRule()

    def test_no_controls_passes(self):
        results = self.rule.check(FdsProject())
        assert results == []

    def test_independent_controls_pass(self):
        p = FdsProject()
        p.add_entity(Control(name="c1", function_type="ANY", input_id="tc1"))
        p.add_entity(Control(name="c2", function_type="ANY", input_id="tc2"))
        results = self.rule.check(p)
        assert results == []

    def test_chain_without_cycle_passes(self):
        p = FdsProject()
        p.add_entity(Control(name="c1", function_type="ANY"))
        p.add_entity(Control(name="c2", function_type="ALL", input_id="c1"))
        p.add_entity(Control(name="c3", function_type="ALL", input_id="c2"))
        results = self.rule.check(p)
        assert results == []

    def test_self_reference_is_error(self):
        p = FdsProject()
        p.add_entity(Control(name="loop", function_type="ANY", input_id="loop"))
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) >= 1

    def test_two_node_cycle_is_error(self):
        p = FdsProject()
        p.add_entity(Control(name="c1", function_type="ANY", input_id="c2"))
        p.add_entity(Control(name="c2", function_type="ANY", input_id="c1"))
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) >= 1

    def test_input_id_pointing_to_devc_not_flagged(self):
        p = FdsProject()
        p.add_entity(Device(name="tc1", x=1, y=1, z=1, quantity="TEMPERATURE"))
        p.add_entity(Control(name="c1", function_type="ANY", input_id="tc1"))
        results = self.rule.check(p)
        assert results == []

class TestFuelSpeciesRule:
    rule = FuelSpeciesRule()

    def test_no_reactions_passes(self):
        results = self.rule.check(FdsProject())
        assert results == []

    def test_fuel_defined_as_spec_passes(self):
        p = FdsProject()
        p.add_entity(Species(name="HEPTANE"))
        p.add_entity(Reaction(name="fire", fuel="HEPTANE", heat_of_combustion=44000.0))
        results = self.rule.check(p)
        assert results == []

    def test_fuel_not_in_spec_is_warning(self):
        p = FdsProject()
        p.add_entity(Reaction(name="fire", fuel="MYSTERY_FUEL", heat_of_combustion=20000.0))
        results = self.rule.check(p)
        warnings = [r for r in results if r.severity == Severity.WARNING]
        assert len(warnings) == 1
        assert "MYSTERY_FUEL" in warnings[0].message

    def test_reaction_with_formula_skips_spec_check(self):
        p = FdsProject()
        p.add_entity(Reaction(name="fire", fuel="PROPANE",
                               formula="C3H8", heat_of_combustion=46000.0))
        results = self.rule.check(p)
        assert results == []

class TestBackingValueRule:
    rule = BackingValueRule()

    def test_valid_backing_void_passes(self):
        p = FdsProject()
        p.add_entity(Surface(name="s", backing="VOID"))
        assert self.rule.check(p) == []

    def test_valid_backing_insulated_passes(self):
        p = FdsProject()
        p.add_entity(Surface(name="s", backing="INSULATED"))
        assert self.rule.check(p) == []

    def test_valid_backing_exposed_passes(self):
        p = FdsProject()
        p.add_entity(Surface(name="s", backing="EXPOSED"))
        assert self.rule.check(p) == []

    def test_valid_backing_air_passes(self):
        p = FdsProject()
        p.add_entity(Surface(name="s", backing="AIR"))
        assert self.rule.check(p) == []

    def test_invalid_backing_is_error(self):
        p = FdsProject()
        p.add_entity(Surface(name="s", backing="CONCRETE"))
        results = self.rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "CONCRETE" in errors[0].message
        assert "s" in errors[0].message

    def test_surface_no_backing_passes(self):
        p = FdsProject()
        s = Surface(name="plain")
        s.backing = ""
        p.add_entity(s)
        assert self.rule.check(p) == []

class TestMeshAspectRatioRule:
    rule = MeshAspectRatioRule()

    def test_cubic_mesh_passes(self):
        p = FdsProject()
        p.add_entity(_mesh(nx=20, ny=20, nz=20, x0=0, x1=4, y0=0, y1=4, z0=0, z1=4))
        results = self.rule.check(p)
        assert results == []

    def test_moderate_aspect_ratio_passes(self):
        p = FdsProject()
        p.add_entity(_mesh(nx=40, ny=20, nz=10, x0=0, x1=4, y0=0, y1=2, z0=0, z1=1))
        results = self.rule.check(p)
        assert results == []

    def test_extreme_aspect_ratio_is_warning(self):
        p = FdsProject()
        # dx=0.2, dy=0.2, dz=2.0 → ratio 10:1
        p.add_entity(_mesh(nx=20, ny=20, nz=1, x0=0, x1=4, y0=0, y1=4, z0=0, z1=2))
        results = self.rule.check(p)
        warnings = [r for r in results if r.severity == Severity.WARNING]
        assert len(warnings) == 1

    def test_empty_project_passes(self):
        assert self.rule.check(FdsProject()) == []

class TestInitBoundsRule:
    rule = InitBoundsRule()

    def test_init_inside_mesh_passes(self):
        p = _project_with_mesh()
        p.add_entity(Init(name="i1", x_min=1, x_max=3, y_min=1, y_max=3,
                          z_min=0.5, z_max=1.5))
        results = self.rule.check(p)
        assert results == []

    def test_init_outside_mesh_is_warning(self):
        p = _project_with_mesh()
        p.add_entity(Init(name="i_far", x_min=10, x_max=12, y_min=10, y_max=12,
                          z_min=0, z_max=1))
        results = self.rule.check(p)
        warnings = [r for r in results if r.severity == Severity.WARNING]
        assert len(warnings) == 1
        assert "i_far" in warnings[0].message

    def test_no_meshes_skips_check(self):
        p = FdsProject()
        p.add_entity(Init(name="i", x_min=0, x_max=1, y_min=0, y_max=1,
                          z_min=0, z_max=1))
        assert self.rule.check(p) == []

    def test_no_inits_passes(self):
        assert self.rule.check(_project_with_mesh()) == []
