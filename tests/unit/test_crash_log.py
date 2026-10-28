"""The desktop programs' log file and last-resort error report (pyfds.gui.crash_log)."""
from __future__ import annotations

import logging
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pyfds.gui import crash_log  # noqa: E402


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    monkeypatch.setenv("PYFDS_USER_DIR", str(tmp_path))
    monkeypatch.setattr(crash_log, "_installed", None)
    monkeypatch.setattr(crash_log, "_last_shown", ("", 0.0))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    log = logging.getLogger("pyfds")
    before = list(log.handlers)
    yield tmp_path
    for h in log.handlers[:]:
        if h not in before:
            log.removeHandler(h)
            h.close()


def test_install_writes_a_log_in_the_user_folder_and_logs_uncaught_errors(fresh, monkeypatch):
    shown = []
    monkeypatch.setattr(crash_log, "_tell_user", lambda exc, path: shown.append((str(exc), path)))
    path = crash_log.install("pyfds_test")
    assert path == str(fresh / "logs" / "pyfds_test.log") and crash_log.install("again") == path
    try:
        raise RuntimeError("boom in a slot")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    text = open(path, encoding="utf-8").read()
    assert "pyfds_test started" in text and "boom in a slot" in text and "Traceback" in text
    assert shown == [("boom in a slot", path)]


def test_the_same_error_is_shown_once_in_a_while(fresh, monkeypatch):
    boxes = []
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: boxes.append(a[2]))
    for _ in range(3):
        crash_log._tell_user(ValueError("paint failed"), "x.log")
    crash_log._tell_user(ValueError("another"), "x.log")
    assert len(boxes) == 2 and "x.log" in boxes[0]
