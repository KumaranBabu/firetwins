"""F5 / F6: the special devices and the Aircoil have their own menu entries, and the generic device takes statistics."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.mw_proxy import main_window_mod as mw  # noqa: E402
from tests.unit.test_main_window_phase2_part1 import _fake_dialog_returning, _make_window  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


def _texts(menu):
    return [a.text().replace("&", "") for a in menu.actions() if not a.isSeparator()]


def _menu(window, title):
    return next(a.menu() for a in window.menuBar().actions() if a.text().replace("&", "") == title)


def test_devices_menu_has_the_special_devices():
    w = _make_window()
    items = _texts(_menu(w, "Devices"))
    for label in ("Add Heat Release Rate Device...", "Add Layer Zoning Device...", "Add Flow Measurement...",
                  "Add Statistics Device...", "Add FED Device...", "Add Aspiration Detection System...",
                  "Add HVAC Output Device...", "Add Time Device..."):
        assert label in items, label
    w.close()


def test_hvac_menu_has_the_aircoil():
    w = _make_window()
    hvac = next(a.menu() for a in _menu(w, "Model").actions() if a.menu() and a.text().replace("&", "") == "HVAC")
    assert "Add Aircoil..." in _texts(hvac)
    w.close()


def test_hrr_device_dialog_creates_an_hrr_device(monkeypatch):
    w = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"quantity": "HRR", "xyz": [1, 1, 1], "name": "HRR1"}))
    w._on_add_hrr_device()
    assert [d.quantity for d in w.api.devices.all()] == ["HRR"]
    w.close()


def test_statistics_device_keeps_its_statistic_and_box(monkeypatch):
    w = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning(
        {"quantity": "TEMPERATURE", "xyz": [1, 1, 1], "name": "S1", "statistics": "MAX",
         "spatial_statistic": "MEAN", "xb": [0, 1, 0, 1, 0, 1]}))
    w._on_add_statistics_device()
    d = w.api.devices.all()[0]
    assert d.statistics == "MAX" and d.spatial_statistic == "MEAN" and tuple(d.xb) == (0, 1, 0, 1, 0, 1)
    w.close()
