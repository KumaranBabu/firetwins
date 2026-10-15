"""Real-solver check for C1: a cluster launch over MPI (host table 'localhost:2', two meshes) and a remote-style
run through the directory provider (stage, run, poll, fetch) must finish with a real FDS and leave its output.
Skipped without ``fds_smv/``."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

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
    a.project.chid = "c1"
    a.project.params.t_end = 0.2
    a.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M1")
    a.meshes.add_mesh([10, 10, 10], [1, 2, 0, 1, 0, 1], name="M2")
    a.meshes.open_boundaries()
    yield a
    for k, v in saved.items():
        cfg.set(k, v)


def test_cluster_launch_over_mpi_on_localhost(api, tmp_path):
    h = api.solvers.run_cluster(["localhost:2"], str(tmp_path))
    assert api.solvers.wait(h, 300)
    assert api.solvers.status(h) == "done", h.message
    assert (tmp_path / "c1.hosts").read_text() == "localhost:2\n"
    assert (tmp_path / "c1.smv").exists() and (tmp_path / "c1.out").exists()


def test_remote_style_run_stages_runs_and_fetches(api, tmp_path):
    h = api.solvers.run_cloud("directory", str(tmp_path / "in"),
                              provider_config={"root": str(tmp_path / "spool"), "fds_binary": str(FDS),
                                               "mpiexec_binary": str(MPIEXEC)}, num_processes=2)
    assert api.solvers.wait(h, 300)
    assert api.solvers.status(h) == "done"
    fetched = api.solvers.fetch(h, str(tmp_path / "results"))
    assert "c1.smv" in fetched and (tmp_path / "results" / "c1.out").exists()
    assert not (tmp_path / "results" / "c1.fds").exists()          # the input is not echoed back


def test_cancel_stops_a_running_cluster_job(api, tmp_path):
    api.project.params.t_end = 600.0
    h = api.solvers.run_cluster(["localhost:2"], str(tmp_path))
    import time
    time.sleep(3)
    api.solvers.cancel(h)
    assert api.solvers.status(h) == "cancelled"
    assert api.solvers.wait(h, 60)
