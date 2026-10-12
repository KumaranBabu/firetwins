"""Unit tests for the PyFDS gap-fill additions: (part 2 of 4)."""


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

@pytest.fixture
def writer():
    return FdsWriter()


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
