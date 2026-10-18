"""The results window's Record / Pause / Resume / Stop controls (V-68) on the real-FDS fixture, offscreen."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.unit.test_results_window import app, win, menu  # noqa: F401  (fixtures and helper)


def _titles(w):
    return [a.text().replace("&", "") for a in menu(w, "File").actions()]


def test_menu_has_record_controls_and_buttons_start_disabled(win):
    t = _titles(win)
    assert any(x.startswith("Record Movie") for x in t) and "Stop Recording" in t
    assert win.rec_btn.isEnabled() and not win.rec_pause_btn.isEnabled() and not win.rec_stop_btn.isEnabled()


def test_record_pause_resume_stop_writes_a_film(win, tmp_path):
    win._quiet = True
    win.open_results(win.smv)
    out = tmp_path / "live.mp4"
    win.record_start(str(out))
    assert not win.rec_btn.isEnabled() and win.rec_stop_btn.isEnabled()
    win.status_rec.text().startswith("REC")
    time.sleep(0.25)
    win._record_tick()
    win.record_pause_resume()
    assert win.rec_pause_btn.text() == "Resume" and "paused" in win.status_rec.text()
    n = win._recorder.frames
    time.sleep(0.2)
    win._record_tick()
    assert win._recorder.frames == n                 # nothing is added while paused
    win.record_pause_resume()
    time.sleep(0.25)
    win._record_tick()
    res = win.record_stop()
    assert res["frames"] > n and Path(res["path"] if res["encoded"] else res["frames_dir"]).exists()
    assert win.rec_btn.isEnabled() and win.status_rec.text() == ""


def test_errors_are_reported_not_raised_by_the_buttons(win):
    win.msgs.clear()
    win._try(win.record_stop, "Record")
    win._try(win.record_pause_resume, "Record")
    assert len(win.msgs) == 2 and "nothing is being recorded" in win.msgs[0]


def test_closing_during_a_recording_ends_the_encoder(win, tmp_path):
    win._quiet = True
    win.record_start(str(tmp_path / "x.mp4"))
    win.close()
    assert win._recorder.state == "stopped"
