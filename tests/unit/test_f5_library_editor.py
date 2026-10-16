"""F5: Edit Libraries - save model items, remove own entries, import/export (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.library_dialog import LibraryDialog  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    return FdsApi()


@pytest.fixture
def dlg(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    d = LibraryDialog(api, None, "materials")
    yield d
    d.close()


def _rows(d):
    return [d.names.item(i).text() for i in range(d.names.count())]


def test_save_model_item_appears_in_the_list_and_counts(dlg, api):
    api.materials.create_default("MYSTEEL")
    assert dlg.model_candidates().count("MYSTEEL") == 1
    before = dlg.category.currentText()
    assert dlg.save_to_library("MYSTEEL", "My steel", "test") == "My steel"
    assert "My steel" in _rows(dlg) and dlg.names.currentItem().text() == "My steel"
    assert dlg.source.text() == "Your library" and dlg.remove_button.isEnabled()
    assert dlg.category.currentText() != before                        # the (n) count moved
    assert api.library.names("materials", "user") == ["My steel"]


def test_duplicate_save_is_refused_and_builtins_cannot_be_removed(dlg, api):
    api.materials.create_default("M1")
    dlg.save_to_library("M1", "dup")
    assert dlg.save_to_library("M1", "dup") is None
    assert dlg.save_to_library("M1", "dup", overwrite=True) == "dup"
    builtin = next(n for n in _rows(dlg) if n not in api.library.names("materials", "user"))
    dlg.names.setCurrentRow(_rows(dlg).index(builtin))
    assert not dlg.remove_button.isEnabled()
    assert dlg.remove_selected() is False or builtin in _rows(dlg)


def test_remove_own_entry(dlg, api):
    api.materials.create_default("M1")
    dlg.save_to_library("M1", "gone")
    assert dlg.remove_selected() and "gone" not in _rows(dlg)
    assert api.library.names("materials", "user") == []


def test_export_then_import_into_a_fresh_project(dlg, api, tmp_path):
    api.materials.create_default("M1")
    dlg.save_to_library("M1", "shared")
    path = str(tmp_path / "lib.json")
    assert dlg.export_file(path) == 1
    other = FdsApi()
    d2 = LibraryDialog(other, None, "materials")
    report = d2.import_file(path, overwrite=False)
    assert report["added"] and "shared" in _rows(d2)
    assert d2.import_file(path, overwrite=False)["added"] == []        # second time: skipped, no duplicate
    d2.close()


def test_bad_files_are_reported_not_fatal(dlg, tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert dlg.import_file(str(bad), overwrite=False) is None


def test_import_fds_syntax_library(dlg, tmp_path):
    f = tmp_path / "lib.fds"
    f.write_text("&MATL ID='FOAM2', DENSITY=30., CONDUCTIVITY=0.04, SPECIFIC_HEAT=1.5 /\n")
    dlg.import_file(str(f), overwrite=False)
    assert "FOAM2" in _rows(dlg)


def test_nothing_to_save_for_an_empty_kind(api, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    d = LibraryDialog(api, None, "spray_models")
    assert d.model_candidates() == [] and d.save_to_library_dialog() is None
    d.close()
