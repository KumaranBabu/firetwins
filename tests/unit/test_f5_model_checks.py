"""F5: the Edit Model Checks dialog and its menu entries (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.editors.model_checks import ModelChecksDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="A")
    return a


@pytest.fixture
def dlg(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    d = ModelChecksDialog(api)
    yield d
    d.close()


def test_lists_every_check_with_its_state(dlg, api):
    assert dlg.names() == [c["name"] for c in api.validation.checks()] and len(dlg.names()) >= 20
    assert all(dlg.states().values()) and not dlg.is_dirty()
    assert "checks on" in dlg.summary.text()


def test_switching_off_is_one_undo_step_and_survives_reopen(dlg, api):
    first, second = dlg.names()[:2]
    dlg.set_state(first, False)
    dlg.set_state(second, False)
    assert dlg.is_dirty() and "2 switched off" in dlg.summary.text()
    assert dlg.apply()
    assert sorted(api.project.disabled_checks) == sorted([first, second])
    assert not ModelChecksDialog(api).states()[first]
    api.history.undo()
    assert api.project.disabled_checks == []


def test_enable_disable_all_respect_the_filter(dlg):
    dlg.filter.setText("mesh")
    shown = [n for r, n in enumerate(dlg.names()) if not dlg.table.isRowHidden(r)]
    assert 0 < len(shown) < len(dlg.names())
    dlg.set_all(False)
    off = [n for n, v in dlg.states().items() if not v]
    assert sorted(off) == sorted(shown)


def test_run_applies_states_and_hands_over_the_report(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    got = []
    d = ModelChecksDialog(api, on_run=got.append)
    d.set_all(False)
    report = d.run()
    assert got == [report] and report.results == []             # nothing enabled -> nothing found
    d.set_all(True)
    assert d.run().results is not None and len(got) == 2
    d.close()


def test_export_and_import_a_check_set(dlg, api, tmp_path):
    name = dlg.names()[0]
    dlg.set_state(name, False)
    path = dlg.export_set(str(tmp_path / "mine.json"))
    assert path and api.project.disabled_checks == [name]
    other = FdsApi()
    d2 = ModelChecksDialog(other)
    assert d2.import_set(path) == [] and not d2.states()[name]
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert d2.import_set(str(bad)) == []                        # refused with a message, no crash
    d2.close()


def test_menu_entries_open_the_dialog_and_run(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    monkeypatch.setattr(ModelChecksDialog, "exec", lambda self: 0)
    w = MainWindow(FdsApi())
    w.action_registry.action("model.edit.checks").trigger()
    assert isinstance(w._model_checks_dialog, ModelChecksDialog)
    w.api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    w.action_registry.action("model.run.checks").trigger()
    assert w.validation_panel.count() >= 0 and w.messages_dock.isVisibleTo(w)
    w.close()
