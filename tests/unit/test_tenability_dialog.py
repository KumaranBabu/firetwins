"""Results window: Analysis > Tenability (FED) (review 2026-10-29, section 3.2)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from pyfds.gui.results.tenability_dialog import TenabilityDialog, guess, tenability, to_ppm
from pyfds.results.viz.csvload import TimeSeries
from pyfds.tenability.fed import calculate_fed


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _series():
    t = np.linspace(0.0, 600.0, 601)
    return {
        "case_devc.csv/CO_1": TimeSeries("CO_1", "VOLUME FRACTION carbon monoxide", "mol/mol", t, np.full_like(t, 5e-3)),
        "case_devc.csv/CO2_1": TimeSeries("CO2_1", "VOLUME FRACTION carbon dioxide", "mol/mol", t, np.full_like(t, 0.02)),
        "case_devc.csv/O2_1": TimeSeries("O2_1", "VOLUME FRACTION oxygen", "mol/mol", t, np.full_like(t, 0.18)),
        "case_devc.csv/TC_1": TimeSeries("TC_1", "TEMPERATURE", "C", t, np.full_like(t, 40.0)),
    }


def test_columns_are_guessed_and_co2_is_not_taken_for_co():
    s = _series()
    assert guess(s, "co") == "case_devc.csv/CO_1" and guess(s, "co2") == "case_devc.csv/CO2_1"
    assert guess(s, "o2") == "case_devc.csv/O2_1" and guess(s, "temp") == "case_devc.csv/TC_1"


def test_units_are_converted_before_the_dose():
    assert to_ppm(np.array([1e-3]), "mol/mol")[0] == pytest.approx(1000.0)
    assert to_ppm(np.array([2.0]), "%")[0] == pytest.approx(20000.0)
    with pytest.raises(ValueError):
        to_ppm(np.array([1.0]), "kg/m3")


def test_result_matches_the_fed_module_and_gives_the_aset_margin():
    s = _series()
    picks = {"co": "case_devc.csv/CO_1", "o2": "case_devc.csv/O2_1", "co2": "case_devc.csv/CO2_1", "temp": None}
    rows = dict(tenability(s, picks, rset_s=60.0))
    t = list(s["case_devc.csv/CO_1"].times)
    ref = calculate_fed(t, [5000.0] * len(t), o2_pct=[18.0] * len(t), co2_pct=[2.0] * len(t))
    assert rows["Time to FED 0.3 (incapacitation, ASET)"] == f"{ref.t_incapacitation:.1f} s"
    assert rows["ASET - RSET"] == f"{ref.t_incapacitation - 60.0:.1f} s"
    with pytest.raises(ValueError):
        tenability(s, {"co": None}, 60.0)


def test_dialog_lists_the_columns_and_calculates(app):
    dlg = TenabilityDialog(SimpleNamespace(csv_series=_series))
    assert dlg.combos["co"].currentData() == "case_devc.csv/CO_1"
    rows = dict(dlg.calculate())
    assert rows["Time to FED 0.3 (incapacitation, ASET)"].endswith(" s")
    dlg.close()


def test_results_window_has_the_entry(app, monkeypatch):
    from pyfds.api.facade import FdsApi
    from pyfds.gui.results.window import ResultsWindow
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    w = ResultsWindow(FdsApi())
    analysis = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Analysis")
    assert "Tenability (FED)..." in [a.text().replace("&", "") for a in analysis.actions()]
    w.close()


def test_compare_runs_dialog_flags_a_changed_device(app, tmp_path):
    from pyfds.gui.results.compare_dialog import CompareRunsDialog
    base, var = tmp_path / "base", tmp_path / "var"
    for d, scale in ((base, 1.0), (var, 1.2)):
        d.mkdir()
        rows = "\n".join(f"{t},{20 + scale * t},{20 + t}" for t in range(0, 61, 10))
        (d / "case_devc.csv").write_text(f's,C,C\nTime,"TC_A","TC_B"\n{rows}\n')
    dlg = CompareRunsDialog(str(base))
    dlg.variant.setText(str(var))
    report = dlg.compare()
    status = {c.name: c.status for c in report.channels}
    assert status == {"TC_A": "warning", "TC_B": "ok"} and dlg.table.rowCount() == 2
    dlg.variant.setText(str(tmp_path / "nowhere"))
    assert dlg.compare() is None and "Choose two" in dlg.summary.text()
    dlg.close()
