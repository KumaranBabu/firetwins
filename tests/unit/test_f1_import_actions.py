"""F1: File > Import / Export entries, Scenarios import and Run > Monitor Simulation (offscreen)."""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.library_dialog import LibraryDialog  # noqa: E402
from pyfds.gui.main_window.actions_import import merge_summary  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def w(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[-1]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append("WARN: " + a[-1]))
    win = MainWindow(FdsApi())
    win.shown = shown
    yield win
    win.close()


@pytest.fixture
def fds_file(tmp_path):
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 2, 0, 2, 0, 2], name="M")
    a.materials.create_default("WOOL")
    a.devices.add_device("TEMPERATURE", [1, 1, 1], name="TC1")
    a.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="BOX")
    f = tmp_path / "in.fds"
    f.write_text(a.fds_text())
    return str(f)


def _action(w, id_):
    return w.action_registry.action(id_)


def test_every_import_and_export_entry_is_real(w):
    for id_ in ("file.import.fds", "file.import.materials", "file.import.scenarios", "file.import.devices",
                "file.import.library", "file.import.config", "file.export.config", "file.export.scenarios",
                "file.export.stl"):
        assert _action(w, id_) is not None and "Coming" not in _action(w, id_).text()
    from pyfds.gui.main_window.placeholders import PLACEHOLDERS
    assert not [k for k in PLACEHOLDERS if any(t in k for t in ("import_", "export_", "monitor_"))]


def test_import_fds_adds_to_the_project_and_summarises(w, fds_file):
    w.api.obstructions.add_obstruction([5, 6, 5, 6, 0, 1], name="BOX")
    r = w._on_import_fds(fds_file)
    assert w.api.meshes.get("M") is not None and w.api.obstructions.get("BOX_2") is not None
    assert len(w.api.obstructions.all()) == 2                               # the project was added to, not replaced
    text = w.shown[-1]
    assert "Added:" in text and "Renamed" in text and "BOX -> BOX_2" in text
    w.api.history.undo()
    assert w.api.meshes.all() == [] and len(w.api.obstructions.all()) == 1


def test_import_materials_and_devices_take_only_their_own_kinds(w, fds_file):
    w._on_import_materials(fds_file)
    assert w.api.materials.get("WOOL") is not None and w.api.devices.all() == [] and w.api.meshes.all() == []
    w._on_import_devices(fds_file)
    assert w.api.devices.get("TC1") is not None and w.api.meshes.all() == []


def test_import_problems_are_shown_not_raised(w, tmp_path):
    assert w._on_import_fds(str(tmp_path / "missing.fds")) is None and w.shown[-1].startswith("WARN")
    empty = tmp_path / "e.fds"
    empty.write_text("! nothing\n")
    assert w._on_import_fds(str(empty)) is None and "no FDS objects" in w.shown[-1]


def test_summary_text_is_readable():
    from types import SimpleNamespace as NS
    class Mesh: pass
    class Obst: pass
    r = {"added": [Mesh(), Obst(), Obst()], "renamed": {"A": "A_2"}, "skipped": ["materials/WOOL"], "warnings": ["w1"]}
    t = merge_summary(r)
    assert "1 Mesh, 2 Obst" in t and "A -> A_2" in t and "materials/WOOL" in t and "1 warning" in t
    assert "nothing" in merge_summary({"added": [], "renamed": {}, "skipped": [], "warnings": []})


def test_scenario_import_export_through_the_menus(w, tmp_path):
    w.api.meshes.add_mesh([5, 5, 5], [0, 4, 0, 4, 0, 3], name="M")
    assert w._on_export_scenario_definitions(str(tmp_path / "none.json")) == 0          # nothing to export yet
    assert "no scenarios" in w.shown[-1]
    w.api.scenarios.create("wide")
    w.api.scenarios.set_override("wide", w.api.meshes.get("M"), "x_max", 8.0)
    f = str(tmp_path / "defs.json")
    assert w._on_export_scenario_definitions(f) == 1
    w.api.scenarios.delete("wide")
    r = w._on_import_scenarios(f)
    assert r["added"] == ["wide"] and "Added 1" in w.shown[-1]
    assert w._on_import_scenarios_dialog.__func__ is not None
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "x"}))
    assert w._on_import_scenarios(str(bad)) is None and "not a PyFDS scenario" in w.shown[-1]


def test_configuration_export_and_import_through_the_menus(w, tmp_path):
    f = str(tmp_path / "cfg.json")
    assert w._on_export_config(f) > 3 and json.loads(open(f).read())["format"] == "pyfds-config"
    r = w._on_import_config(f)
    assert r["applied"] and "Applied" in w.shown[-1]
    bad = tmp_path / "b.json"
    bad.write_text("[]")
    assert w._on_import_config(str(bad)) is None and w.shown[-1].startswith("WARN")


def test_import_library_opens_the_library_dialog(w, monkeypatch):
    monkeypatch.setattr(LibraryDialog, "exec", lambda self: 0)
    assert isinstance(w._on_import_library(), LibraryDialog)


def test_monitor_simulation_needs_a_run_first(w):
    assert w._on_monitor_simulation() is False and "Start a run first" in w.shown[-1]
    watched = []
    w.run_panel.watch = lambda *a, **k: watched.append(a[:3])
    w._last_run_dir = "F:/some/run"
    assert w._on_monitor_simulation() is True
    assert watched == [("F:/some/run", w.api.project.chid, w.api.project.params.t_end)]
