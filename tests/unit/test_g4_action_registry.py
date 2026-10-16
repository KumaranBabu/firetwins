"""G4: declarative menu actions - the registry builds Qt menus from data and the migrated File/Edit menus still
work like the hand-written ones."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from pyfds.gui.actions import EDIT_MENU, FILE_MENU, SEPARATOR, ActionRegistry, ActionSpec, Submenu  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


class Owner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.calls = []

    def _hello(self):
        self.calls.append("hello")

    def _with_arg(self, x):
        self.calls.append(("arg", x))

    def _fill(self):
        self.calls.append("filled")


def _build(items, reg=None):
    owner = Owner()
    reg = reg or ActionRegistry()
    menu = reg.build_menu(owner, owner.menuBar(), "&Test", items, menu_id="test")
    return owner, reg, menu


def test_handlers_attrs_shortcuts_and_state():
    owner, reg, menu = _build([
        ActionSpec("t.hello", "&Hello", "_hello", attr="_hello_action", shortcut="Ctrl+H"),
        ActionSpec("t.arg", "With &arg", ("_with_arg", 7)),
        ActionSpec("t.fn", "Via callable", lambda w: (lambda: w.calls.append("fn"))),
        ActionSpec("t.off", "Off", "_hello", enabled=False),
        ActionSpec("t.check", "Check", "_hello", checkable=True, checked=True),
        SEPARATOR,
        ActionSpec("t.none", "No handler"),
    ])
    reg.action("t.hello").trigger()
    reg.action("t.arg").trigger()
    reg.action("t.fn").trigger()
    assert owner.calls == ["hello", ("arg", 7), "fn"]
    assert owner._hello_action is reg.action("t.hello")
    assert reg.action("t.hello").shortcut().toString() == "Ctrl+H"
    assert not reg.action("t.off").isEnabled() and reg.action("t.check").isChecked()
    reg.set_enabled("t.off", True)
    assert reg.action("t.off").isEnabled()
    assert any(a.isSeparator() for a in menu.actions())
    assert reg.menu("test") is menu


def test_submenus_and_on_built_hook():
    owner, reg, menu = _build([
        Submenu("t.sub", "&Sub", attr="_sub", on_built="_fill", items=[ActionSpec("t.sub.a", "A", "_hello")]),
    ])
    assert owner.calls == ["filled"] and owner._sub is reg.menu("t.sub")
    assert [a.text() for a in owner._sub.actions()] == ["A"]


def test_duplicate_ids_and_unknown_lookups_are_rejected():
    owner = Owner()
    reg = ActionRegistry()
    with pytest.raises(ValueError, match="duplicate"):
        reg.build_menu(owner, owner.menuBar(), "&T", [ActionSpec("x", "A", "_hello"), ActionSpec("x", "B", "_hello")])
    with pytest.raises(KeyError):
        reg.action("nope")


def test_search_and_placeholders():
    _, reg, _ = _build([ActionSpec("t.a", "&Export as FDS...", "_hello"),
                        ActionSpec("t.b", "Print...", "_hello", placeholder=True)])
    assert reg.search("export") == ["t.a"] and reg.search("EXPORT as fds") == ["t.a"]
    assert reg.placeholders() == ["t.b"]


def _all_ids(items):
    for i in items:
        if isinstance(i, Submenu):
            yield from _all_ids(i.items)
        elif i is not SEPARATOR:
            yield i.id


def test_migrated_menus_have_unique_ids_and_real_handlers():
    from pyfds.gui.main_window import MainWindow
    ids = list(_all_ids(FILE_MENU)) + list(_all_ids(EDIT_MENU))
    assert len(ids) == len(set(ids))
    for item in _walk(FILE_MENU) + _walk(EDIT_MENU):
        if isinstance(item.handler, str):
            assert hasattr(MainWindow, item.handler), f"{item.id}: MainWindow has no {item.handler}"
        elif isinstance(item.handler, tuple):
            assert hasattr(MainWindow, item.handler[0])


def _walk(items):
    out = []
    for i in items:
        if isinstance(i, Submenu):
            out += _walk(i.items)
        elif i is not SEPARATOR:
            out.append(i)
    return out


def test_main_window_menus_come_from_the_registry():
    from pyfds.api import FdsApi
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(FdsApi())
    reg = w.action_registry
    assert w._save_action is reg.action("file.save") and w._undo_action is reg.action("edit.undo")
    assert not w._paste_action.isEnabled()
    assert w._recent_submenu is reg.menu("file.recent")
    assert reg.placeholders() == []                      # every File and Edit entry does something now
    assert [a.text() for a in w.menuBar().actions()][:2] == ["&File", "&Edit"]
    assert reg.search("snap") == ["edit.snap"]
    w.close()
