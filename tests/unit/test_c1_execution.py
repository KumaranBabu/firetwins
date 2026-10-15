"""C1: FDS install picker, cluster planning, solver adapters (local / cluster / remote provider),
crash-isolated workers."""
from pathlib import Path

import pytest

from pyfds.api import FdsApi
from pyfds.core.config import get_config
from pyfds.execution import adapters as ad
from pyfds.execution import cluster as cl
from pyfds.execution import installs as ins
from pyfds.execution.isolated import WorkerCrashed, WorkerError, WorkerTimeout, run_isolated

REAL_FDS = Path(__file__).resolve().parents[2] / "fds_smv" / "FDS6" / "bin" / "fds.exe"


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1], name="M1")
    a.meshes.add_mesh([10, 10, 10], [1, 2, 0, 1, 0, 1], name="M2")
    return a


@pytest.fixture
def restore_cfg():
    cfg = get_config()
    keys = ("fds_binary", "mpiexec_binary", "fds_install_name", "fds_installs")
    saved = {k: cfg.get(k) for k in keys}
    yield
    for k, v in saved.items():
        cfg.set(k, v)


# -- installs --------------------------------------------------------------------------------
def test_version_tuple_and_compatibility():
    assert ins.version_tuple("6.10.1") > ins.version_tuple("6.9.1") > ins.version_tuple("6.9")
    assert ins.version_tuple(None) == (0,)
    assert ins.compatibility("6.10.1", "latest")[0]
    assert ins.compatibility("6.10.1", "6.9")[0]
    ok, msg = ins.compatibility("6.7.9", "6.9")
    assert not ok and "older" in msg
    assert ins.compatibility(None, "6.9")[0]


@pytest.mark.skipif(not REAL_FDS.exists(), reason="FDS not installed")
def test_discover_reads_the_real_version_and_select_sets_config(api, restore_cfg):
    found = [i for i in api.solvers.installs() if Path(i.path).resolve() == REAL_FDS.resolve()]
    assert found and found[0].version == "6.10.1" and found[0].mpiexec
    info = api.solvers.select(found[0].name)
    assert info["compatible"] and get_config().get("fds_binary") == str(REAL_FDS) or Path(get_config().get("fds_binary")).resolve() == REAL_FDS.resolve()
    assert api.solvers.selected()["version"] == "6.10.1"
    api.project.fds_version = "6.9"
    assert api.solvers.selected()["compatible"]
    with pytest.raises(KeyError):
        api.solvers.select("FDS 1.0")


def test_probe_of_a_missing_or_wrong_file_is_none(tmp_path):
    assert ins.probe_version(str(tmp_path / "nope.exe")) is None
    junk = tmp_path / "fds.exe"
    junk.write_text("not an executable")
    assert ins.probe_version(str(junk)) is None
    with pytest.raises(FileNotFoundError):
        FdsApi().solvers.add_install(str(tmp_path / "missing"))
    with pytest.raises(ValueError):
        FdsApi().solvers.add_install(str(tmp_path))


# -- cluster planning ------------------------------------------------------------------------
def test_hosts_are_read_in_every_form():
    hs = cl.coerce_hosts(["a:2", ("b", 3), {"name": "c", "processes": 1}, cl.ClusterHost("d"), "e"])
    assert [(h.name, h.processes) for h in hs] == [("a", 2), ("b", 3), ("c", 1), ("d", 1), ("e", 1)]
    with pytest.raises(TypeError):
        cl.coerce_hosts([3.5])


def test_meshes_follow_host_order():
    hs = cl.coerce_hosts(["n1:2", "n2:1", "n3:3"])
    plan = cl.assign_meshes(hs, 6)
    assert [p["meshes"] for p in plan] == [[0, 1], [2], [3, 4, 5]]


def test_validation_rules():
    ok = cl.coerce_hosts(["node1:1", "node2:1"])
    unc = r"\\server\share\case.fds"
    assert cl.validate(ok, unc, 2, windows=True) == []
    assert any("UNC" in p for p in cl.validate(ok, r"C:\cases\case.fds", 2, windows=True))
    assert any("spaces" in p for p in cl.validate(ok, r"\\server\my share\c.fds", 2, windows=True))
    assert any("one process per mesh" in p for p in cl.validate(ok, unc, 3, windows=True))
    assert any("twice" in p for p in cl.validate(cl.coerce_hosts(["a:1", "A:1"]), unc, 2, windows=True))
    assert any("valid host" in p for p in cl.validate(cl.coerce_hosts(["bad host:1", "b:1"]), unc, 2, windows=True))
    assert any("at least one" in p for p in cl.validate(cl.coerce_hosts(["a:0", "b:2"]), unc, 2, windows=True))
    assert any("empty" in p for p in cl.validate([], unc, 2, windows=True))
    assert cl.validate(cl.coerce_hosts(["localhost:2"]), r"C:\local\case.fds", 2, windows=True) == []   # all local
    assert any("absolute" in p for p in cl.validate(ok, "case.fds", 2, windows=False))


def test_machinefile_and_command():
    hs = cl.coerce_hosts(["a:2", "b:1"])
    assert cl.machinefile_text(hs) == "a:2\nb:1\n"
    assert cl.build_command("mpiexec", "fds", "c.fds", hs, "hosts") == [
        "mpiexec", "-machinefile", "hosts", "-n", "3", "fds", "c.fds"]


def test_cluster_dry_run_returns_command_and_plan_without_launching(api, tmp_path):
    h = api.solvers.run_cluster(["localhost:2"], str(tmp_path), dry_run=True)
    assert h.state == ad.DRY_RUN and h.extra["command"][1] == "-machinefile" and h.extra["command"][4] == "2"
    assert h.extra["plan"][0]["meshes"] == [0, 1]
    assert not Path(h.extra["machinefile"]).exists()
    assert (tmp_path / "pyfds_case.fds").is_file()
    assert api.solvers.status(h) == ad.DRY_RUN


def test_cluster_refuses_a_bad_setup(api, tmp_path):
    with pytest.raises(ad.ClusterConfigError) as e:
        api.solvers.run_cluster(["localhost:3"], str(tmp_path), dry_run=True)
    assert "one process per mesh" in str(e.value) and e.value.problems
    plan = api.solvers.cluster_plan(["nodeA:1", "nodeB:1"])
    assert [p["host"] for p in plan["assignment"]] == ["nodeA", "nodeB"]
    assert plan["problems"]                                  # remote nodes need a shared path


# -- adapters --------------------------------------------------------------------------------
def test_local_adapter_dry_run(tmp_path):
    f = tmp_path / "c.fds"
    f.write_text("&HEAD CHID='c'/\n&TAIL/\n")
    h = ad.LocalAdapter().submit(ad.RunRequest(str(f), 1, "fdsx", "mpiexecx", dry_run=True))
    assert h.state == ad.DRY_RUN and h.extra["command"][0] == "fdsx"


class FakeProvider(ad.CloudProvider):
    name = "fake"

    def __init__(self, script=("queued", "running", "done")):
        self.script, self.calls, self.cancelled = list(script), [], False

    def upload(self, input_file):
        self.calls.append(("upload", Path(input_file).name))
        return "job-1"

    def start(self, remote_id, options):
        self.calls.append(("start", options))

    def status(self, remote_id):
        return self.script.pop(0) if len(self.script) > 1 else self.script[0]

    def download(self, remote_id, dest):
        self.calls.append(("download", dest))
        return ["x.smv"]

    def cancel(self, remote_id):
        self.cancelled = True


def _input(tmp_path):
    f = tmp_path / "c.fds"
    f.write_text("&HEAD CHID='c'/\n&TAIL/\n")
    return str(f)


def test_cloud_adapter_lifecycle(tmp_path):
    prov = FakeProvider()
    a = ad.CloudAdapter(prov, fds_version="6.10.1", vcpus=4)
    h = a.submit(ad.RunRequest(_input(tmp_path), 4))
    assert prov.calls[0] == ("upload", "c.fds") and prov.calls[1][1] == {"fds_version": "6.10.1", "vcpus": 4, "num_processes": 4}
    assert a.status(h) == "queued" and a.status(h) == "running"
    assert a.wait(h, 5) and h.state == ad.DONE
    assert a.fetch(h, str(tmp_path / "out")) == ["x.smv"]


def test_cloud_adapter_guards(tmp_path):
    a = ad.CloudAdapter(FakeProvider(("running",)))
    h = a.submit(ad.RunRequest(_input(tmp_path)))
    with pytest.raises(RuntimeError, match="finished"):
        a.fetch(h, str(tmp_path))
    assert a.wait(h, 0.3) is False
    a.cancel(h)
    assert h.state == ad.CANCELLED and a.provider.cancelled
    bad = ad.CloudAdapter(FakeProvider(("exploded",)))
    with pytest.raises(ValueError, match="unknown state"):
        bad.status(bad.submit(ad.RunRequest(_input(tmp_path))))
    assert ad.CloudAdapter(FakeProvider()).submit(ad.RunRequest(_input(tmp_path), dry_run=True)).state == ad.DRY_RUN


def test_provider_registry_and_api_run_cloud(api, tmp_path):
    api.solvers.register_cloud_provider("fake", lambda **kw: FakeProvider(**kw))
    assert "fake" in api.solvers.cloud_providers() and "directory" in api.solvers.cloud_providers()
    h = api.solvers.run_cloud("fake", str(tmp_path / "in"), provider_config={"script": ("done",)}, vcpus=2)
    assert api.solvers.wait(h, 2) and api.solvers.status(h) == "done"
    assert api.solvers.fetch(h, str(tmp_path / "out")) == ["x.smv"]
    with pytest.raises(KeyError):
        api.solvers.run_cloud("nope", str(tmp_path / "in"))
    with pytest.raises(KeyError):
        api.solvers.status("zzz")


# -- isolated workers ------------------------------------------------------------------------
def test_isolated_returns_a_result():
    assert run_isolated("math:sqrt", 49.0, timeout=60) == 7.0


def test_isolated_reports_an_exception_from_the_worker():
    with pytest.raises(WorkerError) as e:
        run_isolated("json:loads", "{not json", timeout=60)
    assert e.value.remote_type == "JSONDecodeError" and "Traceback" in e.value.remote_traceback


def test_isolated_survives_a_crash():
    with pytest.raises(WorkerCrashed) as e:
        run_isolated("os:_exit", 3, timeout=60)
    assert e.value.exitcode == 3


def test_isolated_kills_a_hang():
    with pytest.raises(WorkerTimeout):
        run_isolated("time:sleep", 60, timeout=3)


def test_isolated_rejects_a_bad_target_at_once():
    with pytest.raises(ValueError):
        run_isolated("nocolon")
    with pytest.raises((ImportError, AttributeError)):
        run_isolated("no_such_module_xyz:f")


def test_geometry_import_can_run_isolated(api, tmp_path):
    obj = tmp_path / "cube.obj"
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    faces = [(1, 3, 2), (1, 4, 3), (5, 6, 7), (5, 7, 8), (1, 2, 6), (1, 6, 5), (3, 4, 8), (3, 8, 7), (2, 3, 7), (2, 7, 6), (1, 5, 8), (1, 8, 4)]
    obj.write_text("".join(f"v {x} {y} {z}\n" for x, y, z in verts) + "".join(f"f {a} {b} {c}\n" for a, b, c in faces))
    g = api.geom.import_file(str(obj), isolated=True, name="Cube")
    assert g.name == "Cube" and len(api.geom.all()) == 1
    api.history.undo()
    assert len(api.geom.all()) == 0
    broken = tmp_path / "broken.obj"
    broken.write_text("f 1 2 3\n")
    with pytest.raises(WorkerError):
        api.geom.import_file(str(broken), isolated=True)
    assert len(api.geom.all()) == 0


def test_tools_registered():
    from pyfds.agent.registry import TOOL_REGISTRY
    names = {t.name for t in TOOL_REGISTRY}
    assert {"list_fds_installs", "select_fds_install", "plan_cluster_run", "run_cluster", "run_cloud"} <= names
