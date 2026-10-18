"""SmokeviewRunner: cancel a running render, bundled-binary fallback."""
import sys
import threading

from pyfds.smokeview import runner as runner_mod
from pyfds.smokeview.runner import CANCELLED, SmokeviewRunner


def test_cancel_kills_the_process():
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    rc, _ = SmokeviewRunner._run_cancellable(
        [sys.executable, "-c", "import time; time.sleep(60)"], None, 60, cancel)
    assert rc == CANCELLED


def test_run_returns_exit_code_and_stderr():
    rc, err = SmokeviewRunner._run_cancellable(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"], None, 30, None)
    assert rc == 3 and err == "boom"


def test_default_binary_falls_back_to_bundled(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    resolved = SmokeviewRunner._resolve_binary("smokeview")
    assert resolved.endswith("smokeview.exe") or resolved == "smokeview"


def test_explicit_binary_is_kept(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert SmokeviewRunner._resolve_binary("C:/x/smv.exe") == "C:/x/smv.exe"
    assert runner_mod.CANCELLED < 0
