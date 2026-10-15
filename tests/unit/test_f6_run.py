"""F6: Run FDS dialogs (local / parallel / cluster / cloud), run tracking, stop and cancel, MPI preview and the
Results-menu entries. Unit tests use a fake solver; the real one is in tests/smoke/test_real_fds_f6_run.py."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox  # noqa: E402

from pyfds.api import FdsApi  # noqa: E402
from pyfds.gui.run import model  # noqa: E402
from pyfds.gui.run.dialog import RunDialog  # noqa: E402
from pyfds.gui.run.model import RunSetup  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M1")
    a.meshes.add_mesh([10, 10, 10], [1, 2, 0, 1, 0, 1], name="M2")
    return a


@pytest.fixture(autouse=True)
def no_settings(monkeypatch):
    """Do not touch the registry-backed QSettings."""
    class Dummy:
        def __init__(self, *a): pass
        def value(self, k, d=None): return d
        def setValue(self, k, v): pass
    monkeypatch.setattr("pyfds.gui.run.dialog.QSettings", Dummy)


# -- model --------------------------------------------------------------------------------------------
def test_default_setups(api):
    assert model.default_setup(api, "local").processes == 1
    assert model.default_setup(api, "parallel").processes == 2
    assert model.default_setup(api, "cluster").hosts == ["localhost:2"]
    assert model.default_setup(api, "cloud").options["vcpus"] == 2
    with pytest.raises(ValueError):
        model.default_setup(api, "warp")


def test_problems_per_mode(api, tmp_path):
    ok = RunSetup("local", str(tmp_path))
    assert model.problems(api, ok) == []
    assert any("folder" in p for p in model.problems(api, RunSetup("local")))
    assert any("one process per mesh" in p for p in model.problems(api, RunSetup("parallel", str(tmp_path), processes=3)))
    assert model.problems(api, RunSetup("parallel", str(tmp_path), processes=2)) == []
    empty = FdsApi()
    assert any("no mesh" in p for p in model.problems(empty, RunSetup("local", str(tmp_path))))
    one = FdsApi()
    one.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="Only")
    assert any("at least two" in p for p in model.problems(one, RunSetup("parallel", str(tmp_path), processes=1)))
    assert any("one process per mesh" in p for p in model.problems(api, RunSetup("cluster", str(tmp_path), hosts=["localhost:1"])))
    assert model.problems(api, RunSetup("cluster", str(tmp_path), hosts=["localhost:2"])) == []
    assert any("registered" in p for p in model.problems(api, RunSetup("cloud", str(tmp_path), provider="nope")))
    assert any("spool" in p for p in model.problems(api, RunSetup("cloud", str(tmp_path))))
    assert model.problems(api, RunSetup("cloud", str(tmp_path), provider_config={"root": str(tmp_path)})) == []


def test_validation_errors_block_unless_switched_off(api, tmp_path):
    api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M1b")
    api.meshes.add_mesh([10, 10, 10], [0.5, 1.5, 0, 1, 0, 1], name="Overlap")   # overlapping meshes are an error
    setup = RunSetup("local", str(tmp_path))
    assert any("errors" in p for p in model.problems(api, setup))
    setup.validate_first = False
    assert not any("errors" in p for p in model.problems(api, setup))


def test_assignment_follows_mesh_order(api):
    rows = model.assignment(api, RunSetup("parallel", "x", processes=2))
    assert [r["meshes"] for r in rows] == [[0], [1]]
    rows = model.assignment(api, RunSetup("cluster", "x", hosts=["a:1", "b:1"]))
    assert [(r["host"], r["meshes"]) for r in rows] == [("a", [0]), ("b", [1])]


class FakeSolvers:
    """Records what the GUI asked for and plays back a scripted run."""
    def __init__(self, script=("running", "done")):
        self.calls, self.script, self.state = [], list(script), "running"
        self.handle = SimpleNamespace(id="h1", state="running", message="", extra={}, work_dir="", adapter="local")

    def cloud_providers(self): return ["directory"]
    def cluster_plan(self, hosts, input_file=None):
        from pyfds.execution import cluster as cl
        hs = cl.coerce_hosts(hosts)
        return {"assignment": cl.assign_meshes(hs, sum(h.processes for h in hs)), "problems": []}
    def select(self, name): self.calls.append(("select", name))
    def run_local(self, output_dir, n, validate_first=True): self.calls.append(("local", output_dir, n, validate_first)); return self.handle
    def run_cluster(self, hosts, output_dir, validate_first=True): self.calls.append(("cluster", hosts, output_dir)); return self.handle
    def run_cloud(self, provider, output_dir, cfg, **kw): self.calls.append(("cloud", provider, cfg, kw)); return self.handle
    def status(self, handle):
        if len(self.script) > 1:
            self.state = self.script.pop(0)
        else:
            self.state = self.script[0]
        handle.state = self.state
        return self.state
    def stop(self, handle): self.calls.append(("stop",)); handle.extra["stop_requested"] = True; return "x.stop"
    def cancel(self, handle): self.calls.append(("cancel",)); self.script = ["cancelled"]
    def fetch(self, handle, dest): self.calls.append(("fetch", dest)); return ["a.smv"]
    def preview_model(self, work): self.calls.append(("preview", work)); return os.path.join(work, "p.smv")


def test_start_dispatches_by_mode(api, tmp_path):
    fake = FakeSolvers()
    api.solvers = fake
    model.start(api, RunSetup("local", str(tmp_path), install="FDS 6.10.1"))
    model.start(api, RunSetup("parallel", str(tmp_path), processes=2))
    model.start(api, RunSetup("cluster", str(tmp_path), hosts=["localhost:2"]))
    model.start(api, RunSetup("cloud", str(tmp_path), provider_config={"root": str(tmp_path)}, options={"vcpus": 4}))
    kinds = [c[0] for c in fake.calls]
    assert kinds == ["select", "local", "local", "cluster", "cloud"]
    assert fake.calls[1][2] == 1 and fake.calls[2][2] == 2 and fake.calls[4][3]["vcpus"] == 4
    with pytest.raises(ValueError, match="folder"):
        model.start(api, RunSetup("local"))


# -- dialog ---------------------------------------------------------------------------------------------
def test_dialog_shows_assignment_and_blocks_a_bad_setup(api, tmp_path):
    d = RunDialog(api, "parallel", installs=[])
    assert d.mode_combo.currentData() == "parallel" and d.processes.value() == 2
    assert not d.buttons.button(QDialogButtonBox.Ok).isEnabled() and any("folder" in p for p in d.problems())
    d.folder.setText(str(tmp_path))
    assert d.problems() == [] and d.buttons.button(QDialogButtonBox.Ok).isEnabled()
    assert d.parallel_table.rowCount() == 2 and d.parallel_table.item(0, 2).text() == "1"
    d.processes.setValue(3)
    assert any("one process per mesh" in p for p in d.problems())
    d.processes.setValue(2)
    s = d.setup()
    assert (s.mode, s.processes, s.output_dir) == ("parallel", 2, str(tmp_path))
    d.close()


def test_dialog_cluster_page_edits_hosts_and_previews_meshes(api, tmp_path):
    d = RunDialog(api, "cluster", installs=[])
    d.folder.setText(str(tmp_path))
    assert d.hosts_table.rowCount() == 1 and d.setup().hosts == ["localhost:2"]
    d.hosts_table.item(0, 1).setText("1")
    d.add_host("localhost2", 1)
    assert d.cluster_table.rowCount() == 2 and d.cluster_table.item(1, 2).text() == "2"
    d.hosts_table.selectRow(1)
    d._remove_hosts()
    assert d.setup().hosts == ["localhost:1"] and any("one process per mesh" in p for p in d.problems())
    d.close()


def test_dialog_cloud_page_and_mode_switching(api, tmp_path):
    d = RunDialog(api, "cloud", installs=[])
    d.folder.setText(str(tmp_path))
    assert any("spool" in p for p in d.problems())
    d.spool.setText(str(tmp_path / "spool"))
    d.vcpus.setValue(8)
    d.fds_version.setText("6.10.1")
    s = d.setup()
    assert s.provider == "directory" and s.provider_config == {"root": str(tmp_path / "spool")}
    assert s.options == {"vcpus": 8, "memory_gb_per_vcpu": 2, "fds_version": "6.10.1"}
    d.mode_combo.setCurrentIndex(0)
    assert d.windowTitle() == "Run FDS" and d.pages.currentIndex() == 0 and d.problems() == []
    d.close()


def test_dialog_lists_fds_installs(api):
    inst = SimpleNamespace(name="FDS 6.10.1", path=r"C:\fds\fds.exe")
    d = RunDialog(api, "local", installs=[inst])
    assert d.fds_combo.count() == 2 and d.fds_combo.itemData(1) == "FDS 6.10.1" and d.setup().install is None
    d.fds_combo.setCurrentIndex(1)
    assert d.setup().install == "FDS 6.10.1"
    d.close()


# -- window ---------------------------------------------------------------------------------------------
@pytest.fixture
def win(api, monkeypatch):
    from pyfds.gui.main_window import MainWindow
    w = MainWindow(api)
    w.api.solvers = FakeSolvers()
    w._show_run_monitor = lambda d: None
    shown = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, _n=name, **k: shown.append((_n, a[1], a[2])))
    w._shown = shown
    yield w
    w._run_poll.stop() if getattr(w, "_run_poll", None) else None
    w.close()


def test_run_menu_entries_and_initial_button_state(win):
    ana = next(a.menu() for a in win.menuBar().actions() if a.text() == "&Analysis")
    labels = [a.text().replace("&", "") for a in ana.actions() if a.text()]
    for expected in ("Run FDS Parallel...", "Run FDS Cluster...", "Run FDS Cloud / Remote...", "MPI Preview",
                     "Stop Simulation (write restart file)", "Cancel Simulation (now)"):
        assert expected in labels
    assert not any("Pause" in l for l in labels)
    assert not win._stop_action.isEnabled() and not win._cancel_action.isEnabled()
    assert win._run_parallel_action.isEnabled()


def test_a_run_is_followed_to_completion(win, tmp_path):
    setup = RunSetup("local", str(tmp_path))
    handle = win._on_run_dialog(setup=setup)
    assert handle is win.api.solvers.handle and win._last_run_dir == str(tmp_path)
    assert win._stop_action.isEnabled() and win._cancel_action.isEnabled() and not win._run_parallel_action.isEnabled()
    assert win._poll_run() == "running"
    assert win._poll_run() == "done"
    assert win._shown[-1][:2] == ("information", "Simulation complete")
    assert not win._stop_action.isEnabled() and win._run_parallel_action.isEnabled()


def test_a_second_run_is_refused_while_one_is_active(win, tmp_path):
    win._on_run_dialog(setup=RunSetup("local", str(tmp_path)))
    assert win._on_run_dialog(setup=RunSetup("local", str(tmp_path))) is None
    assert "already running" in win._shown[-1][2]
    assert [c[0] for c in win.api.solvers.calls].count("local") == 1


def test_stop_asks_fds_to_write_a_restart_file_and_is_reported(win, tmp_path):
    win._on_run_dialog(setup=RunSetup("local", str(tmp_path)))
    win._on_stop_simulation()
    assert ("stop",) in win.api.solvers.calls
    win._poll_run(); win._poll_run()
    assert win._shown[-1][1] == "Simulation stopped" and "restart" in win._shown[-1][2]


def test_cancel_and_idle_messages(win, tmp_path):
    win._on_stop_simulation()
    assert "No simulation" in win._shown[-1][2]
    win._on_cancel_simulation()
    assert "No simulation" in win._shown[-1][2]
    win._on_run_dialog(setup=RunSetup("local", str(tmp_path)))
    win._on_cancel_simulation()
    assert ("cancel",) in win.api.solvers.calls and win._run_poll.isActive() is False
    assert win._run_handle.state == "cancelled" and win._run_parallel_action.isEnabled()


def test_a_failed_run_shows_the_reason(win, tmp_path):
    win.api.solvers = FakeSolvers(script=("failed",))
    win.api.solvers.handle.message = "ERROR(101): Problem with MISC line."
    win._on_run_dialog(setup=RunSetup("local", str(tmp_path)))
    win._poll_run()
    assert win._shown[-1][0] == "warning" and "MISC line" in win._shown[-1][2]


def test_cloud_results_are_fetched_into_a_results_folder(win, tmp_path):
    win.api.solvers = FakeSolvers(script=("done",))
    win._on_run_dialog(setup=RunSetup("cloud", str(tmp_path), provider_config={"root": str(tmp_path)}))
    win._poll_run()
    assert ("fetch", str(tmp_path / "results")) in win.api.solvers.calls and win._last_run_dir == str(tmp_path / "results")


def test_dialog_flow_cancelled_and_start_errors(win, monkeypatch, tmp_path):
    monkeypatch.setattr(RunDialog, "exec", lambda self: QDialog.Rejected)
    assert win._on_run_dialog("parallel") is None and win.api.solvers.calls == []
    monkeypatch.setattr(RunDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(RunDialog, "setup", lambda self: RunSetup("local", ""))        # no folder: refused
    assert win._on_run_dialog("local") is None and win._shown[-1][0] == "critical"


def test_mpi_preview_lists_processes_and_meshes(win):
    win._on_mpi_preview()
    kind, title, text = win._shown[-1]
    assert title == "MPI Preview" and "M1" in text and "M2" in text
    win.api.meshes.remove(win.api.meshes.get("M2"))
    win._on_mpi_preview()
    assert "at least two" in win._shown[-1][2]


def test_preview_model_opens_the_viewer_tab(win, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(type(win), "show_results_tab", lambda self, smv=None: opened.append(smv))
    win._current_project_path = str(tmp_path / "case.pyfds")
    smv = win._on_preview_model()
    assert smv == str(tmp_path / "preview" / "p.smv") and opened == [smv]
    def boom(work): raise RuntimeError("FDS not found")
    win.api.solvers.preview_model = boom
    assert win._on_preview_model() is None and win._shown[-1][0] == "critical"


def test_view_results_opens_the_last_run(win, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(type(win), "show_results_tab", lambda self, smv=None: opened.append(smv))
    win._on_view_results()
    assert opened == [None]
    (tmp_path / f"{win.api.project.chid}.smv").write_text("x")
    win._last_run_dir = str(tmp_path)
    win._on_view_results()
    assert opened[-1] == str(tmp_path / f"{win.api.project.chid}.smv")


def test_a_finished_run_is_reported_once(win, tmp_path):
    win._on_run_dialog(setup=RunSetup("local", str(tmp_path)))
    for _ in range(5):
        win._poll_run()
    assert [s[1] for s in win._shown].count("Simulation complete") == 1
