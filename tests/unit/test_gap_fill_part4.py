"""Unit tests for the PyFDS gap-fill additions: (part 4 of 4)."""


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
