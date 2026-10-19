"""Every FDS control function type of the FDS User Guide (Table 18.2), and the CTRL parameters they use, round trip."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pyfds.api import FdsApi
from pyfds.domain.control_functions import CONTROL_FUNCTIONS, problems

_GUIDE_TABLE_18_2 = {"ANY", "ALL", "ONLY", "AT_LEAST", "TIME_DELAY", "CUSTOM", "DEADBAND", "KILL", "RESTART", "SUM", "SUBTRACT",
                     "MULTIPLY", "DIVIDE", "POWER", "EXP", "LOG", "COS", "SIN", "ACOS", "ASIN", "ATAN", "MAX", "MIN", "PID",
                     "PERCENTILE"}          # EXTERNAL (a file-driven control) is not an editable function


def test_every_function_of_the_fds_guide_is_known():
    assert _GUIDE_TABLE_18_2 <= set(CONTROL_FUNCTIONS)


def test_the_new_functions_are_grouped_like_pyrosims_control_types():
    kinds = {n: CONTROL_FUNCTIONS[n].kind for n in ("AT_LEAST", "EXP", "LOG", "SIN", "ATAN", "MAX", "MIN", "PERCENTILE", "PID")}
    assert kinds["AT_LEAST"] == "Detector-based" and set(kinds.values()) - {"Detector-based"} == {"Mathematical"}


def test_at_least_needs_n_and_percentile_needs_its_fraction():
    from pyfds.domain.model import Control
    at_least = Control(name="C1", function_type="AT_LEAST", input_ids=["T1"])
    assert any("needs N" in p for p in problems(at_least))
    at_least.n = 2
    assert problems(at_least) == []
    pct = Control(name="C2", function_type="PERCENTILE", input_ids=["T1"])
    assert any("PERCENTILE_RANK" in p.upper() for p in problems(pct))


def test_pid_is_valid_without_a_set_point():
    api = FdsApi()
    api.devices.add_device("TEMPERATURE", [1, 1, 1], name="T1")
    assert problems(api.controls.add_control("PID", ["T1"], name="PID1")) == []


def test_constant_can_be_set_as_an_input_of_a_math_control():
    api = FdsApi()
    api.devices.add_device("TEMPERATURE", [1, 1, 1], name="T1")
    c = api.controls.add_control("POWER", ["T1"], name="SQ")
    api.controls.set_inputs(c, ["T1", "CONSTANT"])
    assert c.input_ids == ["T1", "CONSTANT"]


_CASE = """&HEAD CHID='c' /
&MESH IJK=4,4,4, XB=0,1,0,1,0,1 /
&DEVC ID='SPEED', XYZ=0.5,0.5,0.5, QUANTITY='VELOCITY' /
&CTRL ID='sq', FUNCTION_TYPE='POWER', INPUT_ID='SPEED','CONSTANT', CONSTANT=2., SETPOINT=10. /
&CTRL ID='pct', FUNCTION_TYPE='PERCENTILE', INPUT_ID='SPEED', PERCENTILE=0.95 /
&CTRL ID='old', FUNCTION_TYPE='PERCENTILE', INPUT_ID='SPEED', PERCENTILE_RANK=0.5 /
&CTRL ID='pid', FUNCTION_TYPE='PID', INPUT_ID='SPEED', TARGET_VALUE=10, PROPORTIONAL_GAIN=0.1, INTEGRAL_GAIN=0.001, DIFFERENTIAL_GAIN=1. /
&TAIL /
"""


def test_constant_percentile_and_pid_parameters_are_read_and_written_with_the_fds_keywords(tmp_path):
    f = tmp_path / "c.fds"
    f.write_text(_CASE)
    api = FdsApi()
    api.session.open_project(str(f))
    sq, pct, old, pid = (api.controls.get(n) for n in ("sq", "pct", "old", "pid"))
    assert sq.constant == 2.0 and pct.percentile_rank == 0.95 and old.percentile_rank == 0.5
    assert (pid.target_value, pid.proportional_gain, pid.integral_gain, pid.differential_gain) == (10.0, 0.1, 0.001, 1.0)
    text = api.fds_text()
    ctrl = {ln.split("'")[1]: ln for ln in text.splitlines() if ln.startswith("&CTRL")}
    assert "CONSTANT=2" in ctrl["sq"] and "PERCENTILE=0.95" in ctrl["pct"] and "PERCENTILE_RANK" not in text
    assert "PERCENTILE=0.5" in ctrl["old"]                                       # an older file is written with the right keyword
    for key in ("TARGET_VALUE=10", "PROPORTIONAL_GAIN=0.1", "INTEGRAL_GAIN=0.001", "DIFFERENTIAL_GAIN=1"):
        assert key in ctrl["pid"]


def test_the_dialog_offers_the_pid_gains_and_the_percentile():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from pyfds.gui.editors.activation_controls import ActivationControlsDialog
    QApplication.instance() or QApplication([])
    api = FdsApi()
    api.devices.add_device("TEMPERATURE", [1, 1, 1], name="T1")
    api.controls.add_control("ANY", ["T1"], name="C")
    dlg = ActivationControlsDialog(api)
    dlg.set_function("PID")
    assert all(not dlg.number_boxes[k].isHidden() for k in ("target_value", "proportional_gain", "integral_gain", "differential_gain"))
    assert dlg.number_boxes["percentile_rank"].isHidden()
    dlg.set_function("PERCENTILE")
    assert not dlg.number_boxes["percentile_rank"].isHidden() and dlg.number_boxes["target_value"].isHidden()
    dlg.number_boxes["percentile_rank"].setValue(0.9)
    assert dlg.pending()["percentile_rank"] == 0.9
    dlg.close()
