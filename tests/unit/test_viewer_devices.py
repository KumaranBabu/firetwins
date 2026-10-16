"""RES-08: devices in the results viewer - positions from the SMV, values from the device CSV, activation from DEVICE_ACT."""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from pyfds.api.facade import FdsApi
from pyfds.api.viz import DevicePoints, pick
from pyfds.gui.results.window import ResultsWindow
from pyfds.results.viz.fds_run import Device, parse_smv

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"
SLICE = "root/FDS Results/2D Slices/TEMPERATURE/T_Y (Y = 1.5)/Mesh 1"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app, tmp_path, monkeypatch):
    shutil.copytree(FIX, tmp_path / "r")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = ResultsWindow(FdsApi())
    w.viewer.open_results(str(tmp_path / "r" / "rroom.smv"))
    yield w
    w.close()


# -- the activation record --------------------------------------------------------------------------------------------
def test_active_at_follows_the_last_change_at_or_before_the_time():
    d = Device("D", activations=[(0.0, 0), (3.62, 1), (9.0, 0)])
    assert [d.active_at(t) for t in (0.0, 3.61, 3.62, 5.0, 9.0, 20.0)] == [False, False, True, True, False, False]
    assert not Device("none").active_at(5.0)                         # no record: never activated
    assert Device("late", activations=[(9.0, 0), (3.0, 1)]).active_at(4.0)       # order in the file does not matter


def test_smv_activations_are_attached_to_their_devices():
    run = parse_smv(str(FIX / "rroom.smv"))
    heat = next(d for d in run.devices if d.name == "HEAT_DET")
    assert (3.62, 1) in heat.activations and not heat.active_at(3.0) and heat.active_at(4.0)
    assert not next(d for d in run.devices if d.name == "TC_060").active_at(100.0)


# -- the data layer ----------------------------------------------------------------------------------------------------
def test_tree_lists_devices_and_they_do_not_stretch_the_timeline(win):
    leaf = win.viewer.tree.find("devices/all")
    assert leaf is not None and leaf.kind == "devices" and "Devices (" in leaf.label
    assert win.viewer.dataset.timeline([leaf]).size == 0


def test_primitive_has_positions_values_and_activation_at_a_time(win):
    ds, leaf = win.viewer.dataset, win.viewer.tree.find("devices/all")
    before = ds.primitives(leaf, 2.0)[0]
    after = ds.primitives(leaf, 8.0)[0]
    assert isinstance(before, DevicePoints) and before.points.shape == (len(before.names), 3)
    i = before.names.index("HEAT_DET")
    assert before.active[i] is False and after.active[i] is True
    assert after.values[i] > before.values[i] > 0                    # temperature rose between the two times
    assert before.units[i] == "C" and before.quantities[i] == "LINK TEMPERATURE"
    assert before.radius > 0
    assert "(activated)" in after.label(i) and "(activated)" not in before.label(i) and "HEAT_DET" in before.label(i)


def test_values_are_interpolated_between_rows_and_missing_data_is_nan(win):
    ds, leaf = win.viewer.dataset, win.viewer.tree.find("devices/all")
    prim = ds.primitives(leaf, 0.16)[0]                              # halfway through the first interval
    assert 19.9 < prim.values[0] < 20.1
    ds.run.devices.append(Device("GHOST", "TEMPERATURE", (1, 1, 1)))
    ghost = ds.primitives(leaf, 1.0)[0]
    assert np.isnan(ghost.values[-1]) and ghost.label(len(ghost.names) - 1) == "GHOST"


def test_run_without_a_device_csv_still_shows_the_devices(win):
    ds, leaf = win.viewer.dataset, win.viewer.tree.find("devices/all")
    ds.run.csv_files = [f for f in ds.run.csv_files if not f.endswith("_devc.csv")]
    ds._devc = None
    prim = ds.primitives(leaf, 5.0)[0]
    assert np.isnan(prim.values).all() and len(prim.names) == len(ds.run.devices)


def test_picking_a_device_names_it_and_gives_its_value():
    p = DevicePoints("Devices", ["A", "B"], np.array([[0.0, 0, 0], [5, 5, 5]]), np.array([20.0, np.nan]), ["C", ""],
                     ["TEMPERATURE", "VELOCITY"], [False, True])
    a = pick.describe("devices/all", "Devices", p, (0.1, 0, 0))
    assert a.kind == "device" and a.label == "A" and a.value == 20.0 and "TEMPERATURE" in a.text
    b = pick.describe("devices/all", "Devices", p, (5, 5, 4.9))
    assert b.label == "B" and b.value is None and "activated" in b.text
    assert pick.describe("devices/all", "Devices", DevicePoints("D", [], np.zeros((0, 3)), np.zeros(0), [], [], []),
                         (0, 0, 0)).kind == "device"


# -- drawing --------------------------------------------------------------------------------------------------------------
def test_the_viewer_draws_blue_and_red_spheres_with_labels(win):
    win.viewer.activate("devices/all")
    win.viewer.activate(SLICE)                                       # devices have no time axis of their own
    win.viewer.set_time(8.0)
    win.sync(True)
    actors = win.view.plotter.renderer.actors
    assert "devices/all#on" in actors and "devices/all#off" in actors and any(k.startswith("devices/all#labels") for k in actors)
    win.viewer.set_time(1.0)                                         # before the heat detector goes off: no red sphere
    win.sync(True)
    assert "devices/all#on" not in win.view.plotter.renderer.actors
    assert "devices/all#off" in win.view.plotter.renderer.actors


def test_devices_are_a_toggle_in_the_tree(win):
    assert "devices" in __import__("pyfds.gui.results.nav_tree", fromlist=["TOGGLE_KINDS"]).TOGGLE_KINDS
