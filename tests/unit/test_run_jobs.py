"""The Run Jobs window: every run of the session, what can be done with each, and the backend behind it."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.execution.adapters import CANCELLED, DONE, QUEUED, RUNNING, RunHandle  # noqa: E402
from pyfds.gui.main_window import MainWindow  # noqa: E402
from pyfds.gui.run.jobs_dialog import JobsDialog  # noqa: E402

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


class Fake:
    """A run adapter whose state the test controls."""

    def __init__(self, fail_status=False):
        self.fail_status, self.cancelled, self.fetched = fail_status, [], []

    def status(self, h):
        if self.fail_status:
            raise ConnectionError("provider unreachable")
        return h.state

    def cancel(self, h):
        self.cancelled.append(h.id)
        h.state = CANCELLED

    def fetch(self, h, dest):
        self.fetched.append(dest)
        return ["a.smv"]


def add(api, kind, state, work_dir, adapter=None, created=None, chid=None):
    h = RunHandle(kind, str(work_dir), state=state)
    if chid:
        h.extra["chid"] = chid
    api.solvers._keep(adapter or Fake(), h)
    if created is not None:
        h.extra["created"] = created
    return h


@pytest.fixture
def api():
    a = FdsApi()
    a.project.params.t_end = 60.0
    return a


# -- backend --------------------------------------------------------------------------------------------------------
def test_jobs_lists_newest_first_with_actions_that_fit_each_state(api, tmp_path):
    shutil.copy(FIX / "rroom_steps.csv", tmp_path / "rroom_steps.csv")
    shutil.copy(FIX / "rroom.smv", tmp_path / "rroom.smv")
    old = add(api, "cloud", DONE, tmp_path / "c", created=100.0, chid="far")
    run = add(api, "local", RUNNING, tmp_path, created=300.0, chid="rroom")
    queued = add(api, "cluster", QUEUED, tmp_path / "q", created=200.0, chid="qq")
    jobs = api.solvers.jobs()
    assert [j["id"] for j in jobs] == [run.id, queued.id, old.id]
    r, q, o = jobs
    assert r["can_stop"] and r["can_cancel"] and not r["can_fetch"] and r["progress"] == "6.0 / 60 s (10%)"
    assert r["smv"] == str(tmp_path / "rroom.smv")
    assert not q["can_stop"] and q["can_cancel"] and q["progress"] == "" and q["smv"] is None
    assert o["can_fetch"] and not o["can_cancel"] and not o["can_stop"]


def test_an_unreachable_provider_shows_as_unknown_not_an_error(api, tmp_path):
    add(api, "cloud", RUNNING, tmp_path, adapter=Fake(fail_status=True), chid="x")
    (j,) = api.solvers.jobs()
    assert j["state"] == "unknown" and "unreachable" in j["message"] and not j["can_stop"]


def test_forget_only_drops_finished_runs(api, tmp_path):
    live = add(api, "local", RUNNING, tmp_path, chid="a")
    done = add(api, "local", DONE, tmp_path, chid="b")
    with pytest.raises(ValueError, match="still going"):
        api.solvers.forget(live)
    api.solvers.forget(done)
    assert [j["id"] for j in api.solvers.jobs()] == [live.id]
    add(api, "cloud", CANCELLED, tmp_path, chid="c")
    add(api, "cloud", RUNNING, tmp_path, adapter=Fake(fail_status=True), chid="d")        # unknown is kept: it may be alive
    assert api.solvers.forget_finished() == 1
    assert sorted(j["chid"] for j in api.solvers.jobs()) == ["a", "d"]


# -- the window --------------------------------------------------------------------------------------------------------
@pytest.fixture
def dlg(api, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    opened = {"results": [], "folder": []}
    d = JobsDialog(api, open_results=opened["results"].append, open_folder=opened["folder"].append, auto_refresh=False)
    d.opened = opened
    yield d
    d.close()


def test_empty_list_says_so_and_all_buttons_are_off(dlg):
    assert dlg.table.rowCount() == 0 and not dlg.empty.isHidden()
    assert not any(b.isEnabled() for b in (dlg.stop_button, dlg.cancel_button, dlg.fetch_button, dlg.results_button,
                                           dlg.folder_button, dlg.clear_button))
    assert dlg.stop_selected() is False and dlg.open_results_selected() is False


def test_rows_show_case_where_state_progress_and_folder(api, dlg, tmp_path):
    shutil.copy(FIX / "rroom_steps.csv", tmp_path / "rroom_steps.csv")
    add(api, "cluster", RUNNING, tmp_path, chid="rroom", created=1.0)
    dlg.refresh()
    row = [dlg.table.item(0, c).text() for c in range(6)]
    assert row[0] == "rroom" and row[1] == "Cluster" and row[2] == "running" and row[3] == "6.0 / 60 s (10%)"
    assert row[5] == str(tmp_path) and dlg.empty.isHidden()


def test_buttons_follow_the_selected_run(api, dlg, tmp_path):
    shutil.copy(FIX / "rroom.smv", tmp_path / "rroom.smv")
    live = add(api, "local", RUNNING, tmp_path, chid="rroom", created=2.0)
    cloud = add(api, "cloud", DONE, tmp_path / "cloud", chid="far", created=1.0)
    dlg.refresh()
    dlg.select(live.id)
    assert dlg.stop_button.isEnabled() and dlg.cancel_button.isEnabled() and not dlg.fetch_button.isEnabled()
    assert dlg.results_button.isEnabled() and dlg.folder_button.isEnabled()
    dlg.select(cloud.id)
    assert dlg.fetch_button.isEnabled() and not dlg.stop_button.isEnabled() and not dlg.results_button.isEnabled()


def test_cancel_stop_fetch_and_open_act_on_the_selected_run(api, dlg, tmp_path, monkeypatch):
    shutil.copy(FIX / "rroom.smv", tmp_path / "rroom.smv")
    fake = Fake()
    live = add(api, "local", RUNNING, tmp_path, adapter=fake, chid="rroom", created=3.0)
    cloud_fake = Fake()
    cloud = add(api, "cloud", DONE, tmp_path / "c", adapter=cloud_fake, chid="far", created=2.0)
    dlg.refresh()
    dlg.select(live.id)
    assert dlg.stop_selected() and (tmp_path / "rroom.stop").exists()              # the clean-stop file FDS watches for
    assert dlg.open_results_selected() and dlg.opened["results"] == [str(tmp_path / "rroom.smv")]
    assert dlg.open_folder_selected() and dlg.opened["folder"] == [str(tmp_path)]
    assert dlg.cancel_selected() and fake.cancelled == [live.id]
    assert dlg.table.item(0, 2).text() == "cancelled"                                # refreshed, selection kept
    dlg.select(cloud.id)
    assert dlg.fetch_selected(dest=str(tmp_path / "got")) and cloud_fake.fetched == [str(tmp_path / "got")]
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))     # chooser cancelled
    assert dlg.fetch_selected() is False and cloud_fake.fetched == [str(tmp_path / "got")]


def test_a_failing_action_is_reported_not_raised(api, dlg, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: seen.append((title, text)))
    h = add(api, "local", QUEUED, tmp_path, chid="q", created=1.0)
    dlg.refresh()
    dlg.select(h.id)
    assert dlg.stop_selected() is False and seen and seen[0][0] == "Stop" and "not running" in seen[0][1]


def test_remove_finished_clears_only_finished_rows(api, dlg, tmp_path):
    add(api, "local", DONE, tmp_path, chid="a", created=1.0)
    live = add(api, "local", RUNNING, tmp_path, chid="b", created=2.0)
    dlg.refresh()
    assert dlg.clear_button.isEnabled()
    assert dlg.remove_finished() == 1 and dlg.table.rowCount() == 1 and dlg.selected_id() is None
    assert [j["id"] for j in dlg._jobs] == [live.id]


# -- the main window -------------------------------------------------------------------------------------------------
def test_run_menu_opens_one_shared_jobs_window(api, tmp_path):
    win = MainWindow(api)
    menus = [m.menu() for m in win.menuBar().actions() if m.menu() is not None]
    assert any(a.text().replace("&", "") == "Run Jobs..." for m in menus for a in m.actions())
    add(api, "local", DONE, tmp_path, chid="a")
    d1 = win._on_run_jobs()
    assert d1.table.rowCount() == 1 and win._on_run_jobs() is d1
    d1.close()
    win.close()
