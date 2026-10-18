"""PyFDS Results > Tools > Data Browsers and Export (slice and boundary lists, device plots, CSV, reports, batch export, Smokeview
movies). These dialogs used to be in the model editor's Results menu; they now belong to the results viewer."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from pyfds.gui.results import window_analysis as mod  # noqa: E402
mw = mod


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_window():
    from pyfds.api import FdsApi
    from pyfds.gui.results.window import ResultsWindow
    return ResultsWindow(FdsApi())


class _FakeSliceEntry:
    def __init__(self, quantity, units, mesh_id, filepath):
        self.quantity, self.units, self.mesh_id, self.filepath = quantity, units, mesh_id, filepath

class _FakeReportDialog:
    def __init__(self, title, text, parent=None):
        pass

    def exec(self):
        return QDialog.Accepted

class _FakeFigureDialog:
    last_title = None
    last_fig = None

    def __init__(self, title, fig, parent=None):
        _FakeFigureDialog.last_title = title
        _FakeFigureDialog.last_fig = fig

    def exec(self):
        return QDialog.Accepted


def test_slice_browser_lists_indexed_slices(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def find_slices(self):
            return [_FakeSliceEntry("TEMP", "C", 1, "case_01.sf")]

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_slice_browser()
    assert "Slice Browser" in captured["title"]
    assert "TEMP" in captured["text"]
    assert "case_01.sf" in captured["text"]
    window.close()

def test_slice_browser_no_data_shows_info_not_report(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def find_slices(self):
            return []

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    monkeypatch.setattr(mw, "TextReportDialog", lambda *a, **k: pytest.fail("must not open report with no data"))
    informed = []
    monkeypatch.setattr(mod.QMessageBox, "information", lambda *a, **k: informed.append(1))
    window._on_slice_browser()
    assert informed
    window.close()

def test_boundary_browser_lists_indexed_boundaries(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def find_boundaries(self):
            return [_FakeSliceEntry("WALL TEMPERATURE", "C", 1, "case_01.bf")]

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    captured = {}

    class _FakeReport:
        def __init__(self, title, text, parent=None):
            captured["title"], captured["text"] = title, text

        def exec(self):
            return QDialog.Accepted

    monkeypatch.setattr(mw, "TextReportDialog", _FakeReport)
    window._on_boundary_browser()
    assert "Boundary Browser" in captured["title"]
    assert "WALL TEMPERATURE" in captured["text"]
    window.close()

def test_export_csv_copies_device_file(monkeypatch, tmp_path):
    window = _make_window()
    src = tmp_path / "case_01_devc.csv"
    src.write_text("Time,TC1\n0.0,20.0\n")
    dest = tmp_path / "exported.csv"
    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def all_device_names(self):
            return ["TC1"]

        def find_device_file(self, name):
            return str(src)

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    monkeypatch.setattr(mod.QInputDialog, "getItem", lambda *a, **k: ("TC1", True))
    monkeypatch.setattr(mod.QFileDialog, "getSaveFileName", lambda *a, **k: (str(dest), ""))
    monkeypatch.setattr(mod.QMessageBox, "information", lambda *a, **k: None)
    window._on_export_csv()
    assert dest.read_text() == src.read_text()
    window.close()

def test_generate_report_saves_with_chosen_format(monkeypatch, tmp_path):
    window = _make_window()
    dest = tmp_path / "report.html"
    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(
        mod.QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(dest), "HTML Report (*.html)"),
    )
    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: None)
    monkeypatch.setattr(mod.QMessageBox, "information", lambda *a, **k: None)
    saved = {}

    class _FakeReport:
        def save(self, filepath, *, fmt="text"):
            saved["filepath"], saved["fmt"] = filepath, fmt

    monkeypatch.setattr(window.api.results, "generate_report", lambda: _FakeReport())
    window._on_generate_report()
    assert saved == {"filepath": str(dest), "fmt": "html"}
    window.close()

def test_batch_export_writes_html_report(monkeypatch, tmp_path):
    window = _make_window()
    dest = tmp_path / "batch_report.html"
    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(mod.QInputDialog, "getText", lambda *a, **k: ("", True))
    monkeypatch.setattr(
        mod.QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(dest), "HTML Report (*.html)"),
    )
    recorded = {}

    class _FakeReport:
        def to_html(self, filepath, title=""):
            recorded["filepath"], recorded["title"] = filepath, title

    def _fake_analyze_batch(output_root, study_name=None, **kwargs):
        recorded["output_root"], recorded["study_name"] = output_root, study_name
        return _FakeReport()

    monkeypatch.setattr(window.api.results, "analyze_batch", _fake_analyze_batch)
    monkeypatch.setattr(mod.QMessageBox, "information", lambda *a, **k: None)
    window._on_batch_export()
    assert recorded["output_root"] == str(tmp_path)
    assert recorded["study_name"] is None  # blank input means "all variants"
    assert recorded["filepath"] == str(dest)
    window.close()

def test_plot_manager_plots_chosen_device(monkeypatch, tmp_path):
    window = _make_window()
    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    class _FakeIndex:
        def all_device_names(self):
            return ["TC1", "TC2"]

        def find_device_file(self, name):
            return "case_01_devc.csv"

    monkeypatch.setattr(window.api.results, "build_index", lambda output_dir: _FakeIndex())
    monkeypatch.setattr(mod.QInputDialog, "getItem", lambda *a, **k: ("TC2", True))
    monkeypatch.setattr(mw, "_figure_dialog", lambda: _FakeFigureDialog)
    monkeypatch.setattr("pyfds.results.reader.DeviceReader.read", staticmethod(lambda filepath: "fake-results"))
    monkeypatch.setattr("pyfds.results.plotters.plot_device_timeseries", lambda results: "fake-fig")
    window._on_plot_manager()
    assert _FakeFigureDialog.last_title == "Plot: TC2"
    assert _FakeFigureDialog.last_fig == "fake-fig"
    window.close()

def _patch_export_animation(monkeypatch, window, *, smv="case.smv", out="a.mp4",
                            accepted=True, values=None, render=None):
    from pyfds.gui.results import window_analysis as mod

    monkeypatch.setattr(mod.QFileDialog, "getOpenFileName", lambda *a, **k: (smv, ""))
    monkeypatch.setattr(mod.QFileDialog, "getSaveFileName", lambda *a, **k: (out, ""))

    class _FakeDialog:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            return mod.QDialog.Accepted if accepted else mod.QDialog.Rejected

        def values(self):
            return values or {"quantity": "TEMPERATURE", "fps": 10,
                              "start_time": 0.0, "end_time": 0.0}

    monkeypatch.setattr(mod, "SchemaFormDialog", _FakeDialog)
    shown = {}
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(mod.QMessageBox, kind,
                            lambda *a, _k=kind, **k: shown.setdefault(_k, a))
    calls = []
    monkeypatch.setattr(window.api.smokeview, "render_movie",
                        render or (lambda *a, **k: calls.append((a, k)) or 0))
    return calls, shown


def _finish_render(window):
    """Wait for the background render thread and deliver its result signal."""
    from PySide6.QtWidgets import QApplication
    worker = getattr(window, "_render_worker", None)
    if worker is not None:
        worker.wait(10000)
        QApplication.processEvents()

def test_export_animation_success(monkeypatch):
    window = _make_window()
    calls, shown = _patch_export_animation(
        monkeypatch, window,
        values={"quantity": "VISIBILITY", "fps": 24, "start_time": 5.0, "end_time": 0.0},
    )
    window._on_export_animation()
    _finish_render(window)
    assert len(calls) == 1
    assert calls[0][0] == ("case.smv", "a.mp4", "VISIBILITY")
    assert {k: v for k, v in calls[0][1].items() if k != "cancel"} == {
        "fps": 24, "start_time": 5.0, "end_time": None}
    assert "information" in shown
    window.close()

def test_export_animation_zero_times_mean_full_range(monkeypatch):
    window = _make_window()
    calls, _ = _patch_export_animation(monkeypatch, window)
    window._on_export_animation()
    _finish_render(window)
    assert calls[0][1]["start_time"] is None and calls[0][1]["end_time"] is None
    window.close()

@pytest.mark.parametrize("cancel", ["smv", "dialog", "out"])
def test_export_animation_cancel_does_not_render(monkeypatch, cancel):
    window = _make_window()
    kwargs = {"smv": "" if cancel == "smv" else "case.smv",
              "out": "" if cancel == "out" else "a.mp4",
              "accepted": cancel != "dialog"}
    calls, _ = _patch_export_animation(monkeypatch, window, **kwargs)
    window._on_export_animation()
    _finish_render(window)
    assert calls == []
    window.close()
def _write_fake_devc_csv(out_dir, chid="room_fire"):
    path = out_dir / f"{chid}_devc.csv"
    path.write_text(
        "Time,tc_center,tc_ceiling,hrr_total\n"
        "s,C,C,kW\n"
        "0.0,20.0,20.0,0.0\n"
        "1.0,21.5,20.5,10.0\n"
        "2.0,24.0,21.0,50.0\n"
    )
    return str(path)

def test_export_animation_nonzero_return_warns(monkeypatch):
    window = _make_window()
    _, shown = _patch_export_animation(monkeypatch, window, render=lambda *a, **k: 3)
    window._on_export_animation()
    _finish_render(window)
    assert "warning" in shown and "information" not in shown
    window.close()

def test_export_animation_exception_shows_critical(monkeypatch):
    window = _make_window()

    def _boom(*a, **k):
        raise RuntimeError("smokeview not found")

    _, shown = _patch_export_animation(monkeypatch, window, render=_boom)
    window._on_export_animation()
    _finish_render(window)
    assert "critical" in shown
    window.close()

def test_view_time_history_shows_figure_dialog(monkeypatch, tmp_path):
    from pyfds.gui.results import window_analysis as mod

    window = _make_window()
    window.api.new(chid="room_fire")
    _write_fake_devc_csv(tmp_path, chid="room_fire")

    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))

    shown = {}

    class _FakeFigureDialog:
        def __init__(self, title, figure, parent=None):
            shown["title"] = title
            shown["figure"] = figure

        def exec(self):
            shown["exec_called"] = True

    monkeypatch.setattr(mod, "_figure_dialog", lambda: _FakeFigureDialog)

    window._on_view_time_history()

    assert shown.get("exec_called") is True
    assert shown["title"] == "Device Time History"
    window.close()

def test_view_time_history_no_devices_shows_info(monkeypatch, tmp_path):
    from pyfds.gui.results import window_analysis as mod

    window = _make_window()
    window.api.new(chid="empty_case")
    # no devc.csv written — build_index() finds nothing

    monkeypatch.setattr(mod.QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    shown = {}
    monkeypatch.setattr(mod.QMessageBox, "information", lambda *a, **k: shown.setdefault("info", True))

    window._on_view_time_history()

    assert shown.get("info") is True
    window.close()

