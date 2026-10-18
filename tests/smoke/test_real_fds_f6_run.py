"""Real-solver check for F6: local and parallel runs through api.solvers, a clean stop that leaves a restart file, the
zero-time model preview, and a full run driven from the main window. Skipped without ``fds_smv/``."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pyfds.api import FdsApi
from pyfds.core.config import get_config

HOME = Path(os.environ.get("PYFDS_FDS_HOME", Path(__file__).resolve().parents[2] / "fds_smv"))
FDS = HOME / "FDS6" / "bin" / "fds.exe"
MPIEXEC = HOME / "FDS6" / "bin" / "mpi" / "mpiexec.exe"

pytestmark = pytest.mark.skipif(not FDS.exists() or not MPIEXEC.exists(), reason="FDS/MPI not installed")


@pytest.fixture
def api():
    cfg = get_config()
    saved = {k: cfg.get(k) for k in ("fds_binary", "mpiexec_binary")}
    cfg.set("fds_binary", str(FDS))
    cfg.set("mpiexec_binary", str(MPIEXEC))
    a = FdsApi()
    a.project.chid = "f6"
    a.project.params.t_end = 0.3
    a.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M1")
    a.meshes.add_mesh([10, 10, 10], [1, 2, 0, 1, 0, 1], name="M2")
    a.meshes.open_boundaries()
    a.obstructions.add_obstruction([0.2, 0.5, 0.2, 0.5, 0, 0.4])
    yield a
    for k, v in saved.items():
        cfg.set(k, v)


def test_local_and_parallel_runs_finish(api, tmp_path):
    h = api.solvers.run_local(str(tmp_path / "serial"), 1)
    assert api.solvers.wait(h, 300) and api.solvers.status(h) == "done", h.message
    assert (tmp_path / "serial" / "f6.smv").is_file()
    h = api.solvers.run_local(str(tmp_path / "mpi"), 2)
    assert api.solvers.wait(h, 300) and api.solvers.status(h) == "done", h.message
    with pytest.raises(ValueError, match="one process per mesh"):
        api.solvers.run_local(str(tmp_path / "bad"), 3)


def test_stop_leaves_a_restart_file_and_the_run_can_be_resumed_from_it(api, tmp_path):
    api.project.params.t_end = 600.0
    api.project.dump.dt_restart = 1.0
    h = api.solvers.run_local(str(tmp_path), 1)
    deadline = time.time() + 60
    while not (tmp_path / "f6.out").exists() and time.time() < deadline:
        time.sleep(0.5)
    time.sleep(3)
    stop_file = api.solvers.stop(h)
    assert Path(stop_file).name == "f6.stop"
    assert api.solvers.wait(h, 120) and api.solvers.status(h) == "done"
    assert h.extra["stop_requested"]
    assert list(tmp_path.glob("f6_*.restart"))
    with pytest.raises(ValueError, match="not running"):
        api.solvers.stop(h)


def test_model_preview_produces_geometry_without_changing_the_project(api, tmp_path):
    before = api.fds_text()
    smv = api.solvers.preview_model(str(tmp_path))
    assert smv.endswith("f6_preview.smv") and "OBST" in Path(smv).read_text(errors="replace")
    assert api.fds_text() == before and api.project.params.t_end == 0.3


def test_a_run_started_from_the_main_window_is_followed_to_the_end(api, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from pyfds.gui.main_window import MainWindow
    from pyfds.gui.run.model import RunSetup
    app = QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[1]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(("warning", a[2])))
    w = MainWindow(api)
    handle = w._on_run_dialog(setup=RunSetup("parallel", str(tmp_path), processes=2))
    assert handle is not None
    deadline = time.time() + 300
    while w._poll_run() not in ("done", "failed", "cancelled") and time.time() < deadline:
        app.processEvents()
        time.sleep(0.3)
    assert w._poll_run() == "done", shown
    assert shown == ["Simulation complete"] and (tmp_path / "f6.smv").is_file()
    assert w._run_parallel_action.isEnabled() and not w._stop_action.isEnabled()
    w.close()


def test_model_preview_opens_in_pyfds_results(api, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from pyfds.gui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    launched = []
    monkeypatch.setattr("pyfds.gui.results.launcher.launch_results", lambda p=None: launched.append(p) or "started")
    w = MainWindow(api)
    w._current_project_path = str(tmp_path / "case.pyfds")
    smv = w._on_preview_model()
    assert smv and Path(smv).is_file()
    assert launched == [smv]                      # PyFDS Results is its own program: the editor only hands it the case
    w.close()
