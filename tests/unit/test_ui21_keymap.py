"""UI-21: keyboard shortcuts can be changed for every menu action, conflicts are caught, changes are saved."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenuBar  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.actions.keymap import Keymap, collect, normalise  # noqa: E402
from pyfds.gui.keymap_dialog import KeymapDialog  # noqa: E402
from pyfds.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def bar():
    b = QMenuBar()
    file = b.addMenu("&File")
    file.addAction("&Open...").setShortcut(QKeySequence("Ctrl+O"))
    file.addSeparator()
    file.addAction("&Save").setShortcut(QKeySequence("Ctrl+S"))
    sub = file.addMenu("&Export")
    sub.addAction("&Save")                                    # same name under another path
    view = b.addMenu("&View")
    view.addAction("&Reset View")
    view.addAction("&Save")
    return b


def test_collect_walks_submenus_and_keeps_ids_unique(bar):
    assert [i for i, _a in collect(bar)] == ["File/Open...", "File/Save", "File/Export/Save", "View/Reset View", "View/Save"]


def test_normalise_gives_portable_text_and_rejects_nonsense():
    assert normalise("ctrl+shift+z") == "Ctrl+Shift+Z" and normalise("  ") == ""
    with pytest.raises(ValueError):
        normalise("not a key")


def test_set_reset_and_defaults(bar):
    km = Keymap(bar)
    assert km.key("File/Open...") == "Ctrl+O" and km.default("File/Open...") == "Ctrl+O"
    km.set("View/Reset View", "ctrl+r")
    assert km.key("View/Reset View") == "Ctrl+R" and km.overrides() == {"View/Reset View": "Ctrl+R"}
    km.set("File/Open...", "")
    assert km.key("File/Open...") == "" and km.default("File/Open...") == "Ctrl+O"
    km.reset("File/Open...")
    assert km.key("File/Open...") == "Ctrl+O"
    km.reset_all()
    assert km.overrides() == {}
    with pytest.raises(KeyError):
        km.set("Nope/Nothing", "F5")


def test_a_key_in_use_is_refused_unless_taken(bar):
    km = Keymap(bar)
    with pytest.raises(ValueError, match="File > Save"):
        km.set("View/Reset View", "Ctrl+S")
    assert km.key("View/Reset View") == ""
    assert km.conflicts("Ctrl+S") == ["File/Save"] and km.conflicts("Ctrl+S", exclude="File/Save") == []
    assert km.set("View/Reset View", "Ctrl+S", steal=True) == ["File/Save"]
    assert km.key("File/Save") == "" and km.key("View/Reset View") == "Ctrl+S"


def test_overrides_round_trip_through_json_and_unknown_ids_are_skipped(bar):
    km = Keymap(bar)
    km.set("View/Reset View", "F6")
    km.set("File/Open...", "")
    text = km.to_json()
    km.reset_all()
    assert km.apply_json(text) == 2 and km.key("View/Reset View") == "F6" and km.key("File/Open...") == ""
    assert km.apply_json('{"Gone/Away": "F9", "View/Save": 5}') == 0           # unknown id, wrong type
    assert km.overrides() == {}                                                  # and everything else went back to default
    assert km.apply_json("not json") == 0 and km.apply_json("[1]") == 0


def test_dialog_lists_filters_assigns_and_saves(bar):
    km = Keymap(bar)
    saved = []
    dlg = KeymapDialog(km, on_save=lambda k: saved.append(k.overrides()))
    assert dlg.table.rowCount() == 5
    dlg.search.setText("reset")
    assert [r for r in range(5) if not dlg.table.isRowHidden(r)] == [3]
    dlg.search.setText("ctrl+s")
    assert [r for r in range(5) if not dlg.table.isRowHidden(r)] == [1]       # matches the key column too
    dlg.search.setText("")
    assert dlg.selected_id() is None and not dlg.assign_button.isEnabled()
    dlg.select("View/Reset View")
    assert dlg.assign_button.isEnabled()
    assert dlg.assign("F6") and saved[-1] == {"View/Reset View": "F6"}
    assert dlg.selected_id() == "View/Reset View"                              # selection survives the refresh
    assert dlg.table.item(3, 1).text() == "F6" and dlg.table.item(3, 1).font().bold()


def test_dialog_conflict_asks_and_can_be_declined_or_accepted(bar):
    km = Keymap(bar)
    dlg = KeymapDialog(km)
    dlg.select("View/Reset View")
    assert dlg.assign("Ctrl+S", steal=False) is False and "already used" in dlg.message.text()
    assert km.key("File/Save") == "Ctrl+S"
    assert dlg.assign("Ctrl+S", steal=True) is True and "File > Save" in dlg.message.text()
    assert km.key("File/Save") == "" and km.key("View/Reset View") == "Ctrl+S"
    dlg.reset_selected()
    assert km.key("View/Reset View") == ""
    dlg.reset_all()
    assert km.key("File/Save") == "Ctrl+S"


def test_main_window_keymap_covers_the_menus_and_survives_a_restart(monkeypatch, tmp_path):
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    try:
        win = MainWindow(FdsApi())
        km = win.keymap
        assert len(km.ids()) > 100
        assert any(r["key"] for r in km.rows())
        target = next(i for i in km.ids() if i.startswith("View/") and km.key(i) == "")
        km.set(target, "Ctrl+Alt+F11")
        win.save_keymap()
        other = MainWindow(FdsApi())
        assert other.keymap.key(target) == ""
        assert other.restore_keymap() == 1 and other.keymap.key(target) == "Ctrl+Alt+F11"
        win.close()
        other.close()
    finally:
        QSettings.setDefaultFormat(QSettings.NativeFormat)


def test_help_menu_opens_the_editor(monkeypatch):
    import pyfds.gui.keymap_dialog as kd
    opened = []
    monkeypatch.setattr(kd.KeymapDialog, "exec", lambda self: opened.append(self.table.rowCount()))
    win = MainWindow(FdsApi())
    win._on_keyboard_shortcuts()
    assert opened and opened[0] > 100
    win.close()
