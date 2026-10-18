"""PyFDS Results is its own program: the editor hands it a case through a small folder (or starts it)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import sys
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pyfds.gui.results import launcher  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


class _Window:
    def __init__(self):
        self.asked = []

    def open_or_refresh(self, path):
        self.asked.append(path)


@pytest.fixture
def server():
    win = _Window()
    srv = launcher.ResultsServer(win, poll_ms=10_000)         # polled by hand
    yield win, srv
    srv.close()


def test_nothing_is_running_until_a_viewer_beats():
    assert not launcher.viewer_running() and launcher.send_open("a.smv") is False


def test_a_running_viewer_receives_the_path(server):
    win, srv = server
    assert launcher.viewer_running()
    assert launcher.send_open("/runs/case.smv") is True
    assert srv.poll() == 1 and win.asked == ["/runs/case.smv"]
    assert srv.poll() == 0                                      # each request is served once


def test_requests_are_served_in_the_order_they_were_made(server):
    win, srv = server
    for name in ("a.smv", "b.smv", "c.smv"):
        launcher.send_open(name)
    srv.poll()
    assert win.asked == ["a.smv", "b.smv", "c.smv"]


def test_a_viewer_can_be_asked_to_come_to_the_front_without_a_file(server):
    win, srv = server
    launcher.send_open(None)
    srv.poll()
    assert win.asked == [None]


def test_a_stale_heartbeat_means_no_viewer(server):
    _, srv = server
    beat = json.loads((launcher.link_dir() / "alive.json").read_text())["t"]
    assert launcher.viewer_running(now=beat + 1) and not launcher.viewer_running(now=beat + launcher.ALIVE_SECONDS + 1)


def test_closing_the_viewer_takes_the_heartbeat_away(server):
    _, srv = server
    srv.close()
    assert not launcher.viewer_running()


def test_old_requests_are_dropped_at_start_but_ones_made_while_it_loaded_are_kept():
    folder = launcher.link_dir()
    folder.mkdir(parents=True, exist_ok=True)
    long_ago = time.time_ns() - int(10 * launcher._STALE_SECONDS * 1e9)
    (folder / f"req_{long_ago:020d}_000001_1.json").write_text(json.dumps({"open": "old.smv"}))
    (folder / f"req_{time.time_ns():020d}_000002_1.json").write_text(json.dumps({"open": "new.smv"}))
    win = _Window()
    srv = launcher.ResultsServer(win, poll_ms=10_000)
    srv.poll()
    assert win.asked == ["new.smv"]
    srv.close()


def test_a_viewer_that_is_still_starting_counts_as_running(monkeypatch):
    class _Proc:
        pid = 4242
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: _Proc())
    launcher.start_results("x.smv")
    assert launcher.viewer_running() and launcher.send_open("y.smv")          # the second click is queued for it


def test_without_a_viewer_one_is_started_and_with_one_it_is_not(monkeypatch, server):
    started = []
    monkeypatch.setattr(launcher, "start_results", lambda p=None: started.append(p))
    assert launcher.launch_results("x.smv") == "sent" and started == []
    server[1].close()
    assert launcher.launch_results("x.smv") == "started" and started == ["x.smv"]


def test_the_command_starts_the_viewer_module_from_source_and_the_exe_when_packaged(monkeypatch, tmp_path):
    assert launcher.results_command("a.smv") == [sys.executable, "-m", "pyfds.gui.results", "a.smv"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "PyFDS.exe"))
    assert launcher.results_command() == [str(tmp_path / "PyFDSResults.exe")]


def test_open_or_refresh_reloads_the_open_case_and_opens_another(tmp_path, monkeypatch):
    from pyfds.api import FdsApi
    from pyfds.gui.results.window import ResultsWindow
    win = ResultsWindow(FdsApi())
    calls = []
    monkeypatch.setattr(ResultsWindow, "refresh", lambda self: calls.append("refresh"))
    monkeypatch.setattr(ResultsWindow, "open_results", lambda self, smv=None: calls.append(("open", smv)))
    a, b = tmp_path / "a.smv", tmp_path / "b.smv"
    a.write_text("x")
    b.write_text("x")
    win.viewer.run = type("R", (), {"path": str(a)})()
    win.open_or_refresh(str(a))
    win.open_or_refresh(str(b))
    assert calls == ["refresh", ("open", str(b))]
    win.viewer.run = None
    win.close()
