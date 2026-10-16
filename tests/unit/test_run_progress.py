"""Run progress: the simulated time of a run, read from the case folder (local or on a network share)."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

from pyfds.api import FdsApi
from pyfds.execution.adapters import RUNNING, RunHandle
from pyfds.execution.progress import describe, read_progress

FIX = Path(__file__).parent.parent / "fixtures" / "results_room"

STEPS = (",,s,s,s\nTime Step,Wall Time,Step Size,Simulation Time,CPU Time\n"
         "       1,2026-10-11T19:18:04.427+05:30, 0.160E+00,   0.15964, 0.59531E+01\n"
         "     200,2026-10-11T19:18:24.606+05:30, 0.161E-01,   5.85303, 0.20609E+02\n")
OUT_STEP = ("       Time Step     {n}   October 11, 2026  19:18:04\n"
            "       Step Size:  0.160E+00 s, Total Time:    {t:.5f} s\n       Pressure Iterations: 1\n")


def test_finished_run_reads_the_end_of_the_real_logs():
    info = read_progress(str(FIX), "rroom", t_end=6.0)
    assert info["finished"] and info["fraction"] == 1.0 and info["time"] == pytest.approx(6.0)
    assert info["step"] == 209 and info["idle"] > 0


def test_steps_csv_gives_the_latest_row(tmp_path):
    (tmp_path / "c_steps.csv").write_text(STEPS)
    info = read_progress(str(tmp_path), "c", t_end=60.0)
    assert info["time"] == pytest.approx(5.85303) and info["step"] == 200
    assert info["fraction"] == pytest.approx(5.85303 / 60) and not info["finished"]
    assert describe(info) == "5.9 / 60 s (10%)"


def test_out_log_is_used_when_there_is_no_steps_file_and_the_larger_time_wins(tmp_path):
    (tmp_path / "c.out").write_text("header\n" + OUT_STEP.format(n=1, t=0.16) + OUT_STEP.format(n=2, t=0.32))
    assert read_progress(str(tmp_path), "c")["time"] == pytest.approx(0.32)
    (tmp_path / "c_steps.csv").write_text(STEPS)                      # newer information in the other file
    assert read_progress(str(tmp_path), "c")["time"] == pytest.approx(5.85303)


def test_nothing_yet_unknown_end_and_overshoot(tmp_path):
    info = read_progress(str(tmp_path / "missing"), "c", t_end=10.0)
    assert info["time"] is None and info["idle"] is None and describe(info) == "waiting for the first step"
    (tmp_path / "c_steps.csv").write_text(STEPS)
    assert describe(read_progress(str(tmp_path), "c")) == "5.9 s"
    assert read_progress(str(tmp_path), "c", t_end=1.0)["fraction"] == 1.0           # never beyond 100 %
    assert read_progress(str(tmp_path), "c", t_end=0)["fraction"] is None


def test_a_half_written_last_line_does_not_break_it(tmp_path):
    (tmp_path / "c_steps.csv").write_text(STEPS + "     210,2026-10-11T19:18:2")
    assert read_progress(str(tmp_path), "c")["time"] == pytest.approx(5.85303)
    (tmp_path / "d.out").write_text(OUT_STEP.format(n=7, t=1.5) + "       Time Step     8   Octo")
    assert read_progress(str(tmp_path), "d")["time"] == pytest.approx(1.5)


def test_idle_grows_when_the_files_stop_changing(tmp_path):
    p = tmp_path / "c_steps.csv"
    p.write_text(STEPS)
    os.utime(p, (time.time() - 90, time.time() - 90))
    assert 85 < read_progress(str(tmp_path), "c")["idle"] < 120


def test_a_large_file_is_only_tailed(tmp_path):
    (tmp_path / "c_steps.csv").write_text(STEPS + "".join(
        f"{i:8d},2026-10-11T19:18:24.606+05:30, 0.1E-01, {i / 100:9.5f}, 0.2E+02\n" for i in range(201, 20000)))
    assert read_progress(str(tmp_path), "c")["time"] == pytest.approx(199.99)


def test_api_progress_follows_a_handle_and_names_the_text(tmp_path):
    api = FdsApi()
    api.project.params.t_end = 60.0
    shutil.copy(FIX / "rroom_steps.csv", tmp_path / f"{api.project.chid}_steps.csv")
    h = RunHandle("cluster", str(tmp_path), state=RUNNING)

    class Adapter:
        pass

    api.solvers._keep(Adapter(), h)
    info = api.solvers.progress(h)
    assert info["text"] == "6.0 / 60 s (10%)" and h.extra["t_end"] == 60.0 and h.extra["chid"] == api.project.chid
    with pytest.raises(KeyError):
        api.solvers.progress("nope")


def test_a_missing_configured_binary_falls_back_to_a_detected_install(monkeypatch, tmp_path):
    from pyfds.execution.installs import FdsInstall

    class Cfg(dict):                                          # stands in for the global config, so nothing leaks
        def set(self, k, v):
            self[k] = v

    api = FdsApi()
    cfg = Cfg(fds_binary=str(tmp_path / "gone" / "fds_local.bat"), mpiexec_binary="old")
    monkeypatch.setattr(api.solvers, "_cfg", lambda: cfg)
    fake = tmp_path / "fds.exe"
    fake.write_text("x")
    monkeypatch.setattr(api.solvers, "installs", lambda probe=True: [FdsInstall("FDS 9", str(fake), "9.0", "mpiexec9", "repo")])
    req = api.solvers._request(str(tmp_path / "a.fds"), 1, True)
    assert req.fds_binary == str(fake) and req.mpiexec_binary == "mpiexec9"
    cfg["fds_binary"] = str(fake)
    monkeypatch.setattr(api.solvers, "installs", lambda probe=True: [])           # a valid configured binary is left alone
    assert api.solvers._request(str(tmp_path / "a.fds"), 1, True).fds_binary == str(fake)


def test_status_bar_shows_where_a_running_run_has_got(tmp_path, monkeypatch):
    import types

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from pyfds.gui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    api = FdsApi()
    api.project.params.t_end = 60.0
    shutil.copy(FIX / "rroom_steps.csv", tmp_path / f"{api.project.chid}_steps.csv")
    win = MainWindow(api)
    h = RunHandle("cluster", str(tmp_path), state=RUNNING)
    api.solvers._keep(object(), h)
    win._run_handle, win._run_setup = h, types.SimpleNamespace(mode="cluster")
    monkeypatch.setattr(api.solvers, "status", lambda handle: "running")
    assert win._poll_run() == "running"
    assert win.statusBar().currentMessage() == "Cluster run: running - 6.0 / 60 s (10%)"
    monkeypatch.setattr(api.solvers, "progress", lambda handle: 1 / 0)             # a broken reader must not stop the poll
    assert win._poll_run() == "running" and win.statusBar().currentMessage() == "Cluster run: running"
    win.close()
