"""
Unit tests for the PyFDS gap-fill additions:

  - 10 new validation rules (rules 13–22)
  - P0 writer bug fixes (all _write_* methods)
  - 4 new writer methods (_write_wind_profile, _write_move,
    _write_hvac_filter, _write_hvac_leakage)
  - New entity collections on FdsProject (wind_profiles, moves,
    hvac_filters, hvac_leakages)
"""
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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _mesh(name="m1", nx=20, ny=20, nz=10,
          x0=0, x1=4, y0=0, y1=4, z0=0, z1=2):
    return Mesh(name=name, cell_count=(nx, ny, nz),
                x_min=x0, x_max=x1, y_min=y0, y_max=y1, z_min=z0, z_max=z1)


def _project_with_mesh(**kw):
    p = FdsProject()
    p.add_entity(_mesh(**kw))
    return p


@pytest.fixture
def writer():
    return FdsWriter()


# ===========================================================================
# SECTION 1 — New validation rules
# ===========================================================================

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


class TestSliceBoundsRule:
    rule = SliceBoundsRule()

    def test_z_slice_inside_mesh_passes(self):
        p = _project_with_mesh(z0=0, z1=2)
        p.add_entity(Slice(name="sl", quantity="TEMPERATURE", plane="Z", position=1.0))
        results = self.rule.check(p)
        assert results == []

    def test_z_slice_outside_mesh_is_warning(self):
        p = _project_with_mesh(z0=0, z1=2)
        p.add_entity(Slice(name="sl_far", quantity="TEMPERATURE", plane="Z", position=5.0))
        results = self.rule.check(p)
        warnings = [r for r in results if r.severity == Severity.WARNING]
        assert len(warnings) == 1
        assert "sl_far" in warnings[0].message

    def test_x_slice_inside_mesh_passes(self):
        p = _project_with_mesh(x0=0, x1=4)
        p.add_entity(Slice(name="sl", quantity="TEMPERATURE", plane="X", position=2.0))
        assert self.rule.check(p) == []

    def test_y_slice_outside_mesh_is_warning(self):
        p = _project_with_mesh(y0=0, y1=4)
        p.add_entity(Slice(name="sl", quantity="TEMPERATURE", plane="Y", position=-1.0))
        results = self.rule.check(p)
        warnings = [r for r in results if r.severity == Severity.WARNING]
        assert len(warnings) == 1

    def test_no_meshes_skips_check(self):
        p = FdsProject()
        p.add_entity(Slice(name="sl", quantity="TEMPERATURE", plane="Z", position=100.0))
        assert self.rule.check(p) == []


class TestNewRulesRegistered:
    """All 10 gap-fill rules must appear in ValidationEngine.default()."""

    def test_all_new_rules_in_default_engine(self):
        engine = ValidationEngine.default()
        names = {r.name for r in engine.rules}
        for expected in [
            "DuplicateId", "VentCoplanar", "DeviceBounds",
            "SurfaceLayer", "CtrlLoop", "FuelSpecies",
            "BackingValue", "MeshAspectRatio", "InitBounds",
            "SliceBounds",
        ]:
            assert expected in names, f"Rule '{expected}' not registered in default engine"

    def test_total_rule_count_is_28(self):
        engine = ValidationEngine.default()
        assert len(engine.rules) == 28


# ===========================================================================
# SECTION 2 — New entity collections on FdsProject
# ===========================================================================

class TestNewEntityCollections:
    def test_wind_profiles_collection_exists(self):
        p = FdsProject()
        assert hasattr(p, "wind_profiles")
        assert isinstance(p.wind_profiles, list)

    def test_moves_collection_exists(self):
        p = FdsProject()
        assert hasattr(p, "moves")
        assert isinstance(p.moves, list)

    def test_hvac_filters_collection_exists(self):
        p = FdsProject()
        assert hasattr(p, "hvac_filters")
        assert isinstance(p.hvac_filters, list)

    def test_hvac_leakages_collection_exists(self):
        p = FdsProject()
        assert hasattr(p, "hvac_leakages")
        assert isinstance(p.hvac_leakages, list)

    def test_add_entity_wind_profile(self):
        p = FdsProject()
        w = WindProfile(name="marine", speed=8.0, direction=270.0)
        p.add_entity(w)
        assert len(p.wind_profiles) == 1
        assert p.wind_profiles[0].name == "marine"

    def test_add_entity_move(self):
        p = FdsProject()
        m = Move(name="spin", omega=2.0)
        p.add_entity(m)
        assert len(p.moves) == 1

    def test_add_entity_hvac_filter(self):
        p = FdsProject()
        f = HvacFilter(name="filt1", duct_id="duct_01", efficiency=0.95)
        p.add_entity(f)
        assert len(p.hvac_filters) == 1

    def test_add_entity_hvac_leakage(self):
        p = FdsProject()
        lk = HvacLeakage(name="gap1", zone_id_1="Z1", zone_id_2="Z2", area=0.002)
        p.add_entity(lk)
        assert len(p.hvac_leakages) == 1

    def test_remove_entity_by_uid_works_for_wind_profile(self):
        p = FdsProject()
        w = WindProfile(name="w")
        p.add_entity(w)
        p.remove_entity_by_uid(w.uid)
        assert p.wind_profiles == []

    def test_type_map_covers_all_new_types(self):
        from pyfds.domain.model import FdsProject as FP
        for cls in (WindProfile, Move, HvacFilter, HvacLeakage):
            assert cls in FP._TYPE_MAP, f"{cls.__name__} missing from _TYPE_MAP"


# ===========================================================================
# SECTION 3 — New namelist writers
# ===========================================================================

class TestWriterWindProfile:
    def test_wind_written(self, writer):
        p = FdsProject()
        p.wind_profiles.append(WindProfile(name="test_wind", speed=5.0, direction=270.0, z_ref=10.0))
        text = writer.generate_content(p)
        assert "&WIND" in text

    def test_wind_speed_and_direction(self, writer):
        p = FdsProject()
        p.wind_profiles.append(WindProfile(name="w", speed=12.5, direction=180.0))
        text = writer.generate_content(p)
        assert "SPEED=12.5" in text
        assert "DIRECTION=180.0" in text

    def test_wind_z_ref(self, writer):
        p = FdsProject()
        p.wind_profiles.append(WindProfile(name="w", speed=5.0, z_ref=20.0))
        text = writer.generate_content(p)
        assert "Z_REF=20.0" in text

    def test_wind_optional_z0(self, writer):
        p = FdsProject()
        p.wind_profiles.append(WindProfile(name="w", speed=5.0, z0=0.03))
        text = writer.generate_content(p)
        assert "Z0=0.03" in text

    def test_wind_optional_latitude(self, writer):
        p = FdsProject()
        p.wind_profiles.append(WindProfile(name="w", speed=5.0, latitude=37.5))
        text = writer.generate_content(p)
        assert "LATITUDE=37.5" in text

    def test_wind_optional_ramp_id(self, writer):
        p = FdsProject()
        p.wind_profiles.append(WindProfile(name="w", speed=0.0, ramp_id="wind_ramp"))
        text = writer.generate_content(p)
        assert "RAMP_ID='wind_ramp'" in text

    def test_wind_omits_absent_optionals(self, writer):
        p = FdsProject()
        p.wind_profiles.append(WindProfile(name="w", speed=5.0))
        text = writer.generate_content(p)
        assert "Z0" not in text
        assert "LATITUDE" not in text
        assert "L_INF" not in text


class TestWriterMove:
    def test_move_written(self, writer):
        p = FdsProject()
        p.moves.append(Move(name="spin", omega=1.0))
        text = writer.generate_content(p)
        assert "&MOVE" in text
        assert "spin" in text

    def test_move_omega(self, writer):
        p = FdsProject()
        p.moves.append(Move(name="m", omega=3.14))
        text = writer.generate_content(p)
        assert "OMEGA=3.14" in text

    def test_move_rotation_angle(self, writer):
        p = FdsProject()
        p.moves.append(Move(name="m", rotation_angle=45.0))
        text = writer.generate_content(p)
        assert "ROTATION_ANGLE=45.0" in text

    def test_move_scale(self, writer):
        p = FdsProject()
        p.moves.append(Move(name="m", scale=2.0))
        text = writer.generate_content(p)
        assert "SCALE=2.0" in text

    def test_move_translation_offsets(self, writer):
        p = FdsProject()
        p.moves.append(Move(name="m", dx=1.0, dy=2.0, dz=3.0))
        text = writer.generate_content(p)
        assert "DX=1.0" in text
        assert "DY=2.0" in text
        assert "DZ=3.0" in text

    def test_move_omits_zero_defaults(self, writer):
        p = FdsProject()
        p.moves.append(Move(name="m"))
        text = writer.generate_content(p)
        # zero offsets and default scale should not be written
        assert "DX" not in text
        assert "SCALE" not in text
        assert "ROTATION_ANGLE" not in text


class TestWriterHvacFilter:
    def test_filter_written(self, writer):
        p = FdsProject()
        p.hvac_filters.append(HvacFilter(name="f1", duct_id="duct_01", efficiency=0.9))
        text = writer.generate_content(p)
        assert "&FILTER" in text
        assert "f1" in text

    def test_filter_efficiency(self, writer):
        p = FdsProject()
        p.hvac_filters.append(HvacFilter(name="f", duct_id="d1", efficiency=0.85))
        text = writer.generate_content(p)
        assert "EFFICIENCY=0.85" in text

    def test_filter_loss(self, writer):
        p = FdsProject()
        p.hvac_filters.append(HvacFilter(name="f", duct_id="d1", loss=2.5))
        text = writer.generate_content(p)
        assert "LOSS=2.5" in text

    def test_filter_clean_loss(self, writer):
        p = FdsProject()
        p.hvac_filters.append(HvacFilter(name="f", duct_id="d1", clean_loss=1.0))
        text = writer.generate_content(p)
        assert "CLEAN_LOSS=1.0" in text

    def test_filter_ctrl_id(self, writer):
        p = FdsProject()
        p.hvac_filters.append(HvacFilter(name="f", duct_id="d1", ctrl_id="ctrl1"))
        text = writer.generate_content(p)
        assert "CTRL_ID='ctrl1'" in text

    def test_filter_omits_absent_clean_loss(self, writer):
        p = FdsProject()
        p.hvac_filters.append(HvacFilter(name="f", duct_id="d1"))
        text = writer.generate_content(p)
        assert "CLEAN_LOSS" not in text


class TestWriterHvacLeakage:
    def test_leak_written(self, writer):
        p = FdsProject()
        p.hvac_leakages.append(HvacLeakage(name="lk", zone_id_1="Z1", zone_id_2="Z2", area=0.001))
        text = writer.generate_content(p)
        assert "&LEAK" in text

    def test_leak_zone_ids(self, writer):
        p = FdsProject()
        p.hvac_leakages.append(HvacLeakage(name="lk", zone_id_1="LOBBY", zone_id_2="CORRIDOR"))
        text = writer.generate_content(p)
        assert "LOBBY" in text
        assert "CORRIDOR" in text

    def test_leak_area(self, writer):
        p = FdsProject()
        p.hvac_leakages.append(HvacLeakage(name="lk", zone_id_1="A", zone_id_2="B", area=0.005))
        text = writer.generate_content(p)
        assert "AREA=0.005" in text

    def test_leak_crack_id(self, writer):
        p = FdsProject()
        p.hvac_leakages.append(HvacLeakage(name="lk", zone_id_1="A", zone_id_2="B",
                                             crack_id="crack1"))
        text = writer.generate_content(p)
        assert "CRACK_ID='crack1'" in text

    def test_leak_ctrl_id(self, writer):
        p = FdsProject()
        p.hvac_leakages.append(HvacLeakage(name="lk", zone_id_1="A", zone_id_2="B",
                                             ctrl_id="ctrl1"))
        text = writer.generate_content(p)
        assert "CTRL_ID='ctrl1'" in text


# ===========================================================================
# SECTION 4 — P0 writer bug fixes
# ===========================================================================

class TestWriterSurfaceP0Fixes:
    def test_geometry_cylindrical_written(self, writer):
        p = FdsProject()
        p.surfaces.append(Surface(name="cyl_surf", geometry="CYLINDRICAL"))
        text = writer.generate_content(p)
        assert "GEOMETRY='CYLINDRICAL'" in text

    def test_rgb_written(self, writer):
        p = FdsProject()
        p.surfaces.append(Surface(name="red_surf", rgb=(255, 0, 0)))
        text = writer.generate_content(p)
        assert "RGB=255,0,0" in text

    def test_volume_flow_written(self, writer):
        p = FdsProject()
        p.surfaces.append(Surface(name="exhaust", volume_flow=0.5))
        text = writer.generate_content(p)
        assert "VOLUME_FLOW=0.5" in text

    def test_mass_flux_written(self, writer):
        p = FdsProject()
        p.surfaces.append(Surface(name="inject", mass_flux=0.01))
        text = writer.generate_content(p)
        assert "MASS_FLUX=0.01" in text

    def test_ramp_v_written(self, writer):
        p = FdsProject()
        p.surfaces.append(Surface(name="supply", ramp_v="vel_ramp"))
        text = writer.generate_content(p)
        assert "RAMP_V='vel_ramp'" in text

    def test_tmp_back_written(self, writer):
        p = FdsProject()
        p.surfaces.append(Surface(name="wall", tmp_back=20.0))
        text = writer.generate_content(p)
        assert "TMP_BACK=20.0" in text

    def test_texture_width_written(self, writer):
        p = FdsProject()
        p.surfaces.append(Surface(name="tex", texture_map="brick.png",
                                   texture_width=0.3, texture_height=0.15))
        text = writer.generate_content(p)
        assert "TEXTURE_WIDTH=0.3" in text
        assert "TEXTURE_HEIGHT=0.15" in text

    def test_absent_optional_fields_omitted(self, writer):
        p = FdsProject()
        p.surfaces.append(Surface(name="plain"))
        text = writer.generate_content(p)
        assert "VOLUME_FLOW" not in text
        assert "MASS_FLUX" not in text
        assert "RAMP_V" not in text
        assert "TMP_BACK" not in text


class TestWriterSpeciesP0Fixes:
    def test_spec_id_list_written(self, writer):
        p = FdsProject()
        p.species.append(Species(name="AIR_MIX",
                                  spec_id=["NITROGEN", "OXYGEN"],
                                  volume_fraction=[0.79, 0.21]))
        text = writer.generate_content(p)
        assert "SPEC_ID=" in text
        assert "NITROGEN" in text

    def test_volume_fraction_written(self, writer):
        p = FdsProject()
        p.species.append(Species(name="MIX", spec_id=["N2", "O2"],
                                  volume_fraction=[0.79, 0.21]))
        text = writer.generate_content(p)
        assert "VOLUME_FRACTION=0.79,0.21" in text

    def test_mass_fraction_written(self, writer):
        p = FdsProject()
        p.species.append(Species(name="MIX", spec_id=["CO2"],
                                  mass_fraction=[1.0]))
        text = writer.generate_content(p)
        assert "MASS_FRACTION=1.0" in text

    def test_radcal_id_written(self, writer):
        p = FdsProject()
        p.species.append(Species(name="SOOT", radcal_id="SOOT_DEFAULT"))
        text = writer.generate_content(p)
        assert "RADCAL_ID='SOOT_DEFAULT'" in text

    def test_absent_spec_id_omitted(self, writer):
        p = FdsProject()
        p.species.append(Species(name="simple"))
        text = writer.generate_content(p)
        assert "VOLUME_FRACTION" not in text
        assert "MASS_FRACTION" not in text


class TestWriterVentP0Fixes:
    def test_dynamic_pressure_written(self, writer):
        p = FdsProject()
        p.vents.append(Vent(name="wind", x_min=0, x_max=4, y_min=0, y_max=4,
                             z_min=2, z_max=2, surface_id="OPEN",
                             dynamic_pressure=50.0))
        text = writer.generate_content(p)
        assert "DYNAMIC_PRESSURE=50.0" in text

    def test_devc_id_written(self, writer):
        p = FdsProject()
        p.vents.append(Vent(name="ctrl_vent", x_min=0, x_max=1, y_min=0, y_max=1,
                             z_min=0, z_max=0, surface_id="OPEN",
                             devc_id="opener"))
        text = writer.generate_content(p)
        assert "DEVC_ID='opener'" in text

    def test_rgb_written_on_vent(self, writer):
        p = FdsProject()
        p.vents.append(Vent(name="v", x_min=0, x_max=1, y_min=0, y_max=1,
                             z_min=0, z_max=0, surface_id="OPEN",
                             rgb=(0, 128, 255)))
        text = writer.generate_content(p)
        assert "RGB=0,128,255" in text

    def test_absent_vent_fields_omitted(self, writer):
        p = FdsProject()
        p.vents.append(Vent(name="plain", x_min=0, x_max=1, y_min=0, y_max=1,
                             z_min=0, z_max=0, surface_id="OPEN"))
        text = writer.generate_content(p)
        assert "DYNAMIC_PRESSURE" not in text
        assert "DEVC_ID" not in text


class TestWriterDeviceP0Fixes:
    def test_initial_state_true_written(self, writer):
        p = FdsProject()
        p.devices.append(Device(name="d", x=1, y=1, z=1, quantity="TEMPERATURE",
                                 initial_state=True))
        text = writer.generate_content(p)
        assert "INITIAL_STATE=.TRUE." in text

    def test_spatial_statistic_written(self, writer):
        p = FdsProject()
        p.devices.append(Device(name="d", x=1, y=1, z=1, quantity="TEMPERATURE",
                                 spatial_statistic="MAX"))
        text = writer.generate_content(p)
        assert "SPATIAL_STATISTIC='MAX'" in text

    def test_points_written(self, writer):
        p = FdsProject()
        p.devices.append(Device(name="d", x=0, y=0, z=0, quantity="TEMPERATURE",
                                 points=10))
        text = writer.generate_content(p)
        assert "POINTS=10" in text

    def test_vd_to_vd_written(self, writer):
        p = FdsProject()
        p.devices.append(Device(name="d", x=1, y=1, z=1, quantity="VOLTAGE",
                                 vd_to_vd=True))
        text = writer.generate_content(p)
        assert "VD_TO_VD=.TRUE." in text

    def test_absent_device_fields_omitted(self, writer):
        p = FdsProject()
        p.devices.append(Device(name="d", x=1, y=1, z=1, quantity="TEMPERATURE"))
        text = writer.generate_content(p)
        assert "SPATIAL_STATISTIC" not in text
        assert "POINTS" not in text
        assert "VD_TO_VD" not in text


class TestWriterParticleP0Fixes:
    def test_spec_id_written(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="droplet", spec_id="WATER VAPOR"))
        text = writer.generate_content(p)
        assert "SPEC_ID='WATER VAPOR'" in text

    def test_vaporization_temperature_written(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="drop", vaporization_temperature=100.0))
        text = writer.generate_content(p)
        assert "VAPORIZATION_TEMPERATURE=100.0" in text

    def test_heat_of_vaporization_written(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="drop", heat_of_vaporization=2257.0))
        text = writer.generate_content(p)
        assert "HEAT_OF_VAPORIZATION=2257.0" in text

    def test_n_strata_written_when_nondefault(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="drop", n_strata=12))
        text = writer.generate_content(p)
        assert "N_STRATA=12" in text

    def test_gamma_written(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="drop", gamma=1.4))
        text = writer.generate_content(p)
        assert "GAMMA=1.4" in text

    def test_sigma_written(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="drop", sigma=0.07))
        text = writer.generate_content(p)
        assert "SIGMA=0.07" in text

    def test_quantities_written(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="pt", quantities=["PARTICLE DIAMETER",
                                                             "PARTICLE TEMPERATURE"]))
        text = writer.generate_content(p)
        assert "QUANTITIES=" in text
        assert "PARTICLE DIAMETER" in text

    def test_orientation_written(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="pt", orientation=(0.0, 0.0, 1.0)))
        text = writer.generate_content(p)
        assert "ORIENTATION=0.0,0.0,1.0" in text

    def test_ctrl_id_written_on_particle(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="pt", ctrl_id="sprinkler_ctrl"))
        text = writer.generate_content(p)
        assert "CTRL_ID='sprinkler_ctrl'" in text

    def test_absent_particle_fields_omitted(self, writer):
        p = FdsProject()
        p.particles.append(Particle(name="plain"))
        text = writer.generate_content(p)
        assert "VAPORIZATION_TEMPERATURE" not in text
        assert "QUANTITIES" not in text
        assert "ORIENTATION" not in text


class TestWriterPropP0Fixes:
    def test_particle_velocity_written(self, writer):
        p = FdsProject()
        p.props.append(Prop(name="sprk", particle_velocity=5.0))
        text = writer.generate_content(p)
        assert "PARTICLE_VELOCITY=5.0" in text

    def test_characteristic_velocity_written(self, writer):
        p = FdsProject()
        p.props.append(Prop(name="sprk", characteristic_velocity=2.0))
        text = writer.generate_content(p)
        assert "CHARACTERISTIC_VELOCITY=2.0" in text

    def test_length_written(self, writer):
        p = FdsProject()
        p.props.append(Prop(name="sensor", length=0.1))
        text = writer.generate_content(p)
        assert "LENGTH=0.1" in text

    def test_smokeview_id_written(self, writer):
        p = FdsProject()
        p.props.append(Prop(name="det", smokeview_id="SMOKE_DETECTOR"))
        text = writer.generate_content(p)
        assert "SMOKEVIEW_ID='SMOKE_DETECTOR'" in text

    def test_smokeview_parameters_written(self, writer):
        p = FdsProject()
        p.props.append(Prop(name="det", smokeview_parameters=[0.1, 0.2, 0.3]))
        text = writer.generate_content(p)
        assert "SMOKEVIEW_PARAMETERS=0.1,0.2,0.3" in text

    def test_absent_prop_fields_omitted(self, writer):
        p = FdsProject()
        p.props.append(Prop(name="plain"))
        text = writer.generate_content(p)
        assert "PARTICLE_VELOCITY" not in text
        assert "SMOKEVIEW_ID" not in text


class TestWriterMaterialP0Fixes:
    def test_nu_gases_written(self, writer):
        p = FdsProject()
        p.materials.append(Material(name="WOOD", nu_gases=[0.1, 0.2]))
        text = writer.generate_content(p)
        assert "NU_GASES=0.1,0.2" in text

    def test_spec_ids_written(self, writer):
        p = FdsProject()
        p.materials.append(Material(name="WOOD", spec_ids=["CO2", "H2O"]))
        text = writer.generate_content(p)
        assert "SPEC_ID='CO2','H2O'" in text

    def test_pyrolysis_range_written(self, writer):
        p = FdsProject()
        p.materials.append(Material(name="WOOD", pyrolysis_range=50.0))
        text = writer.generate_content(p)
        assert "PYROLYSIS_RANGE=50.0" in text

    def test_reference_rate_written(self, writer):
        p = FdsProject()
        p.materials.append(Material(name="WOOD", reference_rate=0.001))
        text = writer.generate_content(p)
        assert "REFERENCE_RATE=0.001" in text

    def test_per_reaction_nu_spec_written(self, writer):
        p = FdsProject()
        mat = Material(name="PYRO", n_reactions=2,
                       reactions=[
                           MaterialReaction(nu_spec=[0.8, 0.2]),
                           MaterialReaction(nu_spec=[0.6, 0.4]),
                       ])
        p.materials.append(mat)
        text = writer.generate_content(p)
        assert "NU_SPEC=" in text

    def test_absent_material_fields_omitted(self, writer):
        p = FdsProject()
        p.materials.append(Material(name="PLAIN"))
        text = writer.generate_content(p)
        assert "PYROLYSIS_RANGE" not in text
        assert "NU_GASES" not in text
        assert "REFERENCE_RATE" not in text


class TestWriterHvacP0Fixes:
    def test_node_duct_id_written(self, writer):
        p = FdsProject()
        p.hvac_nodes.append(HvacNode(name="n1", x=0, y=0, z=0, duct_id="duct_01"))
        text = writer.generate_content(p)
        assert "DUCT_ID='duct_01'" in text

    def test_node_filter_id_written(self, writer):
        p = FdsProject()
        p.hvac_nodes.append(HvacNode(name="n1", x=0, y=0, z=0, filter_id="filt_01"))
        text = writer.generate_content(p)
        assert "FILTER_ID='filt_01'" in text

    def test_duct_area_written(self, writer):
        p = FdsProject()
        p.hvac_ducts.append(HvacDuct(name="d1", node_id_1="n1", node_id_2="n2",
                                      diameter=0.5, area=0.196))
        text = writer.generate_content(p)
        assert "AREA=0.196" in text

    def test_duct_perimeter_written(self, writer):
        p = FdsProject()
        p.hvac_ducts.append(HvacDuct(name="d1", node_id_1="n1", node_id_2="n2",
                                      diameter=0.5, perimeter=1.57))
        text = writer.generate_content(p)
        assert "PERIMETER=1.57" in text

    def test_duct_leakage_id_written(self, writer):
        p = FdsProject()
        p.hvac_ducts.append(HvacDuct(name="d1", node_id_1="n1", node_id_2="n2",
                                      diameter=0.5, leakage_id="lk1"))
        text = writer.generate_content(p)
        assert "LEAKAGE_ID='lk1'" in text

    def test_duct_loss_pair_written(self, writer):
        p = FdsProject()
        p.hvac_ducts.append(HvacDuct(name="d1", node_id_1="n1", node_id_2="n2",
                                      diameter=0.5, loss=(1.5, 2.0)))
        text = writer.generate_content(p)
        assert "LOSS=" in text

    def test_fan_max_flow_written(self, writer):
        p = FdsProject()
        p.fans.append(Fan(name="fan1", duct_id="d1", max_flow=0.5))
        text = writer.generate_content(p)
        assert "MAX_FLOW=0.5" in text

    def test_fan_max_pressure_written(self, writer):
        p = FdsProject()
        p.fans.append(Fan(name="fan1", duct_id="d1", max_pressure=200.0))
        text = writer.generate_content(p)
        assert "MAX_PRESSURE=200.0" in text

    def test_fan_volume_flow_curve_written(self, writer):
        p = FdsProject()
        p.fans.append(Fan(name="fan1", duct_id="d1",
                          volume_flow=[0.0, 0.25, 0.5], pressure=[200.0, 150.0, 0.0]))
        text = writer.generate_content(p)
        assert "VOLUME_FLOW=" in text
        assert "PRESSURE=" in text

    def test_fan_absent_fields_omitted(self, writer):
        p = FdsProject()
        p.fans.append(Fan(name="fan1", duct_id="d1"))
        text = writer.generate_content(p)
        # Isolate the &FAN line to avoid false matches against &PRES MAX_PRESSURE_ITERATIONS
        fan_line = next(ln for ln in text.splitlines() if ln.startswith("&FAN"))
        assert "MAX_FLOW" not in fan_line
        assert "MAX_PRESSURE" not in fan_line
        assert "VOLUME_FLOW" not in fan_line

    def test_node_absent_ids_omitted(self, writer):
        p = FdsProject()
        p.hvac_nodes.append(HvacNode(name="n1", x=0, y=0, z=0))
        text = writer.generate_content(p)
        assert "FILTER_ID" not in text
