"""DEVC time statistics and Freeze Output (PyroSim HVAC/other devices), and two device keys real FDS rejects."""
from __future__ import annotations

from pyfds.api import FdsApi


def _devc_line(api, name):
    return next(ln for ln in api.fds_text().splitlines() if ln.startswith("&DEVC") and f"ID='{name}'" in ln)


def test_time_statistic_and_freeze_output_are_written_with_the_fds_keywords():
    api = FdsApi()
    api.devices.add_device("TEMPERATURE", [0.5, 0.5, 0.5], name="D1")
    d = api.devices.get("D1")
    d.temporal_statistic, d.no_update_devc_id = "MAX", "D1"
    line = _devc_line(api, "D1")
    assert "TEMPORAL_STATISTIC='MAX'" in line and "NO_UPDATE_DEVC_ID='D1'" in line


def test_smoothed_data_becomes_the_smoothed_statistic_and_vd_to_vd_is_not_written():
    api = FdsApi()
    api.devices.add_device("TEMPERATURE", [0.5, 0.5, 0.5], name="D1")
    d = api.devices.get("D1")
    d.smoothed_data, d.vd_to_vd = True, True
    line = _devc_line(api, "D1")
    assert "TEMPORAL_STATISTIC='SMOOTHED'" in line and "SMOOTHED_DATA" not in line and "VD_TO_VD" not in line


def test_the_new_keys_are_read_back(tmp_path):
    f = tmp_path / "d.fds"
    f.write_text("&HEAD CHID='d' /\n&MESH IJK=4,4,4, XB=0,1,0,1,0,1 /\n"
                 "&DEVC ID='T', XYZ=0.5,0.5,0.5, QUANTITY='TEMPERATURE', TEMPORAL_STATISTIC='RUNNING AVERAGE', NO_UPDATE_CTRL_ID='K' /\n&TAIL /\n")
    api = FdsApi()
    api.session.open_project(str(f))
    d = api.devices.get("T")
    assert d.temporal_statistic == "RUNNING AVERAGE" and d.no_update_ctrl_id == "K"
    assert "TEMPORAL_STATISTIC" not in (d.fds_extra or {})
