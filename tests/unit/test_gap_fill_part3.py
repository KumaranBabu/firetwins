"""Unit tests for the PyFDS gap-fill additions: (part 3 of 4)."""


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


@pytest.fixture
def writer():
    return FdsWriter()


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
        assert "NU_SPEC=0.1,0.2" in text      # FDS 6.10.1 rejects NU_GASES

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
        assert "NU_SPEC" not in text and "NU_MATL" not in text
        assert "REFERENCE_RATE" not in text
