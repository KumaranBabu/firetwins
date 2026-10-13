"""Real-solver check for the B4 inputs: FDS 6.10 must accept what the API writes for HVAC (jet fan, fan curve,
filter, aircoil, damper), detector systems (beam, aspiration, FED, dry pipe, stop control), smoke settings and
particle kinds, and the activation/HRR summaries must read what it writes. Skipped without ``fds_smv/``."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyfds.api import FdsApi

HOME = Path(os.environ.get("PYFDS_FDS_HOME", Path(__file__).resolve().parents[2] / "fds_smv"))
FDS = HOME / "FDS6" / "bin" / "fds.exe"

pytestmark = pytest.mark.skipif(not FDS.exists(), reason="FDS not installed")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("real_b4")
    api = FdsApi()
    api.project.chid = "b4"
    api.meshes.add_mesh(ijk=(40, 20, 20), xb=(0, 8, 0, 4, 0, 4), name="M")
    api.meshes.open_boundaries()
    api.reactions.add_simple_reaction("PROPANE", 46000.0, soot_yield=0.01)
    api.reactions.set_smoke(mass_extinction_coefficient=7600.0, visibility_factor=8.0, maximum_visibility=20.0)
    api.fires.add_from_library("t2 fast", [3.4, 4.0, 1.4, 2.0, 0], peak_kw=300.0, name="FIRE")
    # HVAC: jet fan, and a small duct system with a filter, damper and aircoil
    api.hvac.add_jet_fan([6.0, 2.0, 2.0], "+x", width=1.0, height=1.0, thrust=30.0, name="JF")
    api.hvac_nodes.add_node([1, 1, 3], name="A")
    api.hvac_nodes.add_node([2, 1, 3], name="B")
    api.hvac_nodes.add_node([3, 1, 3], ambient=True, name="C")
    api.hvac_nodes.add_node([0.5, 1, 3], ambient=True, name="Z")
    api.hvac_ducts.add_duct("Z", "A", area=0.1, name="D0")
    api.hvac_ducts.add_duct("A", "B", area=0.1, name="D1")
    api.hvac_ducts.add_duct("B", "C", area=0.1, name="D2")
    api.fans.add_fan("D0", max_flow=0.5, max_pressure=200.0, name="F0")
    api.fans.set_curve("F0", [0.0, 0.25, 0.5], [200.0, 150.0, 0.0])
    api.species.add_species("PARTICULATE", mw=28.0, mass_fraction_0=0.001, specific_heat=1.0)
    api.hvac_filters.add_filter("D1", node_id="A", efficiency=0.9, spec_id="PARTICULATE", clean_loss=1.0, loss=50.0, name="FLT")
    api.hvac_aircoils.add_aircoil("D2", 0.5, coolant_temperature=10.0, coolant_specific_heat=4.186,
                                  coolant_mass_flow=1.0, name="COIL")
    api.devices.add_hvac_output("DUCT VOLUME FLOW", duct_id="D0", name="Q0")
    api.devices.add_hvac_output("NODE PRESSURE DIFFERENCE", node_id=["Z", "A"], name="DP")
    # detectors
    api.devices.add_beam_detector([0.5, 7.5, 3.5, 3.5, 3.5, 3.5], setpoint=33.0, name="BEAM")
    api.devices.add_aspiration_system([7, 3, 3.5], [{"xyz": [1, 3, 3.9], "flowrate": 0.1, "delay": 5.0},
                                                    {"xyz": [3, 3, 3.9], "flowrate": 0.2, "delay": 2.0}],
                                      setpoint=0.5, bypass_flowrate=0.1, name="ASP")
    api.devices.add_fed_device([4, 1.5, 1.8], activity=3, name="FED1")
    api.devices.add_fed_device([4, 1.5, 1.8], quantity="FIC", name="FIC1")
    api.particles.add_droplet("WATER")
    api.props.add_prop("NOZ", part_id="WATER", flow_rate=30.0, particle_velocity=10.0, spray_angle=(0, 60))
    api.devices.add_dry_pipe_sprinkler([4, 1.5, 3.8], "NOZ", delay=1.0, rti=20.0, activation_temperature=40.0, name="SPK")
    api.particles.add_tracer("TR")
    api.devices.add_thermocouple([4, 1.5, 3.8], "HOT", setpoint=1500.0)
    api.devices.stop_when("HOT")
    api.egress.add_outputs(1.8)
    api.config.configure_simulation(t_end=6.0)
    result = api.execution.run(str(out), fds_binary=str(FDS), timeout=900)
    return api, out, result


def test_fds_accepts_all_of_it(run):
    api, out, result = run
    log = (out / "b4.out").read_text(errors="replace")
    assert result.success, (result.error, result.return_code, [l for l in log.splitlines() if "ERROR" in l][:3])
    assert "ERROR" not in log and "STOP: FDS completed successfully" in log


def test_hrr_summary_and_activation_table_read_the_real_files(run):
    api, out, _ = run
    s = api.results.hrr_summary(str(out), "b4")
    assert s["peak_hrr_kw"] > 0 and s["total_energy_mj"] > 0 and s["duration_s"] == pytest.approx(6.0, abs=0.1)
    rows = api.results.activation_table(str(out), "b4")
    assert isinstance(rows, list) and all(r["time"] >= 0 for r in rows)
