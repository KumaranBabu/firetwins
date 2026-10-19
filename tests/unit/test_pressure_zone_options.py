"""Simulation Parameters > "Disable pressure zones" and "Minimum zone volume" (MISC NO_PRESSURE_ZONES / MINIMUM_ZONE_VOLUME)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pyfds.api import FdsApi


def _misc_line(api):
    return next(ln for ln in api.fds_text().splitlines() if ln.startswith("&MISC"))


def test_the_options_are_written_only_when_set():
    api = FdsApi()
    assert "NO_PRESSURE_ZONES" not in _misc_line(api) and "MINIMUM_ZONE_VOLUME" not in _misc_line(api)
    api.project.misc.no_pressure_zones = True
    api.project.misc.minimum_zone_volume = 0.5
    line = _misc_line(api)
    assert "NO_PRESSURE_ZONES=.TRUE." in line and "MINIMUM_ZONE_VOLUME=0.5" in line


def test_the_options_are_read_from_an_fds_file(tmp_path):
    f = tmp_path / "z.fds"
    f.write_text("&HEAD CHID='z' /\n&MESH IJK=4,4,4, XB=0,1,0,1,0,1 /\n&MISC NO_PRESSURE_ZONES=.TRUE., MINIMUM_ZONE_VOLUME=2.0 /\n&TAIL /\n")
    api = FdsApi()
    api.session.open_project(str(f))
    assert api.project.misc.no_pressure_zones is True and api.project.misc.minimum_zone_volume == 2.0
    assert "NO_PRESSURE_ZONES" not in (api.project.misc.fds_extra or {})          # a typed field now, not an extra


def test_the_dialog_has_both_options_on_the_misc_tab():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from pyfds.gui.editors.sim_params import specs_for
    QApplication.instance() or QApplication([])
    specs = {s.name: s for s in specs_for(FdsApi(), "environment")}
    assert specs["no_pressure_zones"].label == "Disable pressure zones" and specs["minimum_zone_volume"].units == "m3"
