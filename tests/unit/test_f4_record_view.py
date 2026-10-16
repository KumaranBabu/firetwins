"""F4: the Record View - line/object mapping (no Qt), highlighting, following the model, selection both ways."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from pyfds.api import FdsApi
from pyfds.gui.record_view import model as rm

TEXT = """&HEAD CHID='c' /

&SURF ID='Wall', COLOR='GRAY' /
&MESH ID='M', XB=0.0,1.0,0.0,1.0,0.0,1.0, IJK=10,10,10 /
free text outside a record
&RAMP ID='R', T=0.0, F=0.0 /
&RAMP ID='R', T=1.0, F=1.0 /
&TAIL /
"""


def _api():
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M")
    a.surfaces.create_default("Wall")
    a.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], "Wall", name="Box")
    a.devices.add_thermocouple([0.5, 0.5, 0.5], "T1")
    a.ramps.add_ramp("R", [0, 1], [0, 1])
    return a


# -- logic ---------------------------------------------------------------------------------------------
def test_index_finds_records_ids_and_collections():
    recs = rm.index_records(TEXT)
    assert [(r.line, r.tag, r.name, r.attr) for r in recs] == [
        (0, "HEAD", None, None), (2, "SURF", "Wall", "surfaces"), (3, "MESH", "M", "meshes"),
        (5, "RAMP", "R", "ramps"), (6, "RAMP", "R", "ramps"), (7, "TAIL", None, None)]
    assert rm.record_at(recs, 3).name == "M" and rm.record_at(recs, 4) is None
    assert rm.lines_of(recs, "ramps", "R") == [5, 6] and rm.lines_of(recs, "ramps", "X") == []
    assert rm.summary(recs)["RAMP"] == 2


def test_entity_lookup():
    a = _api()
    recs = rm.index_records(a.fds_text())
    box = next(r for r in recs if r.tag == "OBST")
    assert rm.entity_for(a, box).name == "Box"
    assert rm.entity_for(a, next(r for r in recs if r.tag == "HEAD")) is None
    assert rm.entity_for(a, rm.RecordLine(0, "OBST", "Missing", "obstructions")) is None


def test_ids_with_quotes_and_spaces():
    recs = rm.index_records("&DEVC ID='TC 1', QUANTITY='TEMPERATURE' /\n  &obst id = 'x' /")
    assert [(r.tag, r.name) for r in recs] == [("DEVC", "TC 1"), ("OBST", "x")]


# -- the widget ------------------------------------------------------------------------------------------
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from pyfds.gui.record_view import RecordView  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


def _formats(view, line):
    return view.editor.document().findBlockByNumber(line).layout().formats()


def _color_at(view, line, col):
    for f in _formats(view, line):
        if f.start <= col < f.start + f.length:
            c = f.format.foreground().color().name()
    return c


def test_shows_the_fds_text_and_counts_records():
    a = _api()
    v = RecordView(a)
    assert v.text() == a.fds_text() and v.editor.toPlainText() == a.fds_text() and v.editor.isReadOnly()
    assert "records" in v.status.text() and "RAMP 2" in v.status.text()
    v.close()


def test_syntax_colours():
    a = _api()
    v = RecordView(a)
    n = next(r.line for r in v.records() if r.tag == "OBST")
    line = v.text().split("\n")[n]
    tag = _color_at(v, n, 1)                               # & OBST
    key = _color_at(v, n, line.index("XB"))
    string = _color_at(v, n, line.index("'Box'") + 1)
    number = _color_at(v, n, line.index("XB=") + 4)
    assert len({tag, key, string, number}) == 4
    assert _color_at(v, n, 1) == tag and tag in ("#0b5394", "#6fb1ff")
    v.close()


def test_free_text_is_greyed_and_records_are_not():
    a = _api()
    v = RecordView(a)
    v.editor.setPlainText("note outside any record\n&HEAD CHID='x' /")
    grey = _color_at(v, 0, 2)
    assert grey in ("#888888", "#8a8a8a") and _color_at(v, 1, 1) != grey
    v.close()


def test_follows_the_model_after_a_short_delay_and_keeps_the_scroll_position():
    a = _api()
    v = RecordView(a, debounce_ms=0)
    before = v.text()
    a.obstructions.add_obstruction([2, 3, 0, 1, 0, 1], "Wall", name="Second")
    assert v.text() == before                                # nothing until the timer fires
    v.schedule_refresh()
    v._timer.timeout.emit()
    assert "Second" in v.text() and v.text() == a.fds_text()
    v.refresh()                                              # unchanged: nothing to do
    v.close()


def test_selecting_an_object_marks_and_scrolls_to_its_record():
    a = _api()
    v = RecordView(a)
    ramp = a.ramps.get("R")
    assert v.show_entity("ramps", ramp)
    marks = v.editor.extraSelections()
    assert len(marks) == 2                                    # one line per ramp point
    assert all("RAMP" in m.cursor.selectedText() for m in marks)
    assert v.editor.textCursor().blockNumber() == v.records()[[r.name for r in v.records()].index("R")].line
    assert not v.show_entity("obstructions", type("X", (), {"name": "nope"})())
    assert v.editor.extraSelections() == []
    v.close()


def test_clicking_a_record_selects_its_object():
    a = _api()
    picked = []
    v = RecordView(a, on_select=lambda attr, e: picked.append((attr, e.name)))
    line = next(r.line for r in v.records() if r.tag == "OBST")
    from PySide6.QtGui import QTextCursor
    v.editor.setTextCursor(QTextCursor(v.editor.document().findBlockByNumber(line)))
    assert picked == [("obstructions", "Box")]
    assert v.entity_at_line(line).name == "Box" and v.entity_at_line(0) is None
    v.follow.setChecked(False)
    v.editor.setTextCursor(QTextCursor(v.editor.document().findBlockByNumber(0)))
    v.editor.setTextCursor(QTextCursor(v.editor.document().findBlockByNumber(line)))
    assert len(picked) == 1                                   # not following: no more selections
    v.close()


def test_find_wraps_and_reports_misses():
    a = _api()
    v = RecordView(a)
    assert v.find("surf") and v.editor.textCursor().selectedText().lower() == "surf"
    first = v.editor.textCursor().position()
    assert v.find("surf")
    assert v.editor.textCursor().position() != first or v.text().lower().count("surf") == 1
    assert not v.find("zzz_not_there") and "not found" in v.status.text()
    assert not v.find("")
    assert v.find("surf", backwards=True)
    v.close()


def test_copy_and_save(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    a = _api()
    v = RecordView(a)
    v.copy_all()
    assert QApplication.clipboard().text() == a.fds_text()
    out = tmp_path / "x.fds"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a_, **k: (str(out), ""))
    assert v.save_as() == str(out) and out.read_text(encoding="utf-8") == a.fds_text()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a_, **k: ("", ""))
    assert v.save_as() is None
    v.close()


# -- in the main window ----------------------------------------------------------------------------------
def test_record_tab_in_the_main_window(monkeypatch):
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(_api())
    view_menu = next(a.menu() for a in w.menuBar().actions() if a.text() == "&View")
    labels = [a.text().replace("&", "") for a in view_menu.actions()]
    assert labels[:3] == ["Show 3D View", "Show 2D View", "Show Record View"]
    obst = w.api.obstructions.get("Box")
    w.explorer.select_entity("obstructions", obst)
    view = w.show_record_tab()
    assert w.view_tabs.tabText(w.view_tabs.currentIndex()) == "Record" and w.show_record_tab() is view
    assert [m.cursor.selectedText() for m in view.editor.extraSelections()][0].startswith("&OBST")
    w.api.obstructions.add_obstruction([5, 6, 0, 1, 0, 1], "Wall", name="Later")
    view._timer.timeout.emit()
    w._on_status_event(None)
    view.refresh()
    assert "Later" in view.text()
    other = w.api.obstructions.get("Later")
    w.explorer.select_entity("obstructions", other)         # selection in the tree moves the mark
    assert "Later" in view.editor.extraSelections()[0].cursor.selectedText()
    # clicking a record selects the object in the tree
    line = next(r.line for r in view.records() if r.name == "Box" and r.tag == "OBST")
    from PySide6.QtGui import QTextCursor
    view.editor.setTextCursor(QTextCursor(view.editor.document().findBlockByNumber(line)))
    assert w.explorer.selected()[1].name == "Box"
    w.show_model_tab()
    assert w.view_tabs.currentWidget() is w.model_split
    idx = w.view_tabs.indexOf(view)
    w._on_close_view_tab(idx)
    assert w._record_view is None and w.view_tabs.indexOf(view) == -1
    w.close()
