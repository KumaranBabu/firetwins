"""A2 — scenario run scripts, model-check sets, the run gate, live checking, click-through."""
from __future__ import annotations

import json

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.api.checks import ValidationGateError
from pyfds.io.serializer import Serializer


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name="M")
    return a


# ---------------------------------------------------------------- FIR-07
def _two_scenarios(api):
    api.obstructions.add_obstruction(xb=[0.2, 0.4, 0.2, 0.4, 0, 0.2], name="Box")
    api.scenarios.create("Base")
    api.scenarios.create("NoBox")
    api.scenarios.set_override("NoBox", "Box", "enabled", False)


def test_export_all_writes_run_all_scripts(api, tmp_path):
    _two_scenarios(api)
    written = api.scenarios.export_all(str(tmp_path), fds_command="C:/FDS/fds.exe")
    assert set(written) == {"Base", "NoBox"}
    bat = (tmp_path / "run_all.bat").read_bytes().decode()
    assert "\r\n" in bat                                         # real Windows line endings
    assert 'set "FDS=C:/FDS/fds.exe"' in bat
    assert bat.index('pushd "%~dp0Base"') < bat.index('pushd "%~dp0NoBox"')   # in order
    assert '"%FDS%" Base.fds' in bat and "FAILED" in bat and "exit /b %FAILED%" in bat
    sh = (tmp_path / "run_all.sh").read_text()
    assert sh.startswith("#!/bin/sh") and '"$FDS" NoBox.fds' in sh and "\r" not in sh
    assert (tmp_path / "Base" / "Base.fds").exists()


def test_run_scripts_use_mpiexec_for_parallel(tmp_path):
    from pyfds.api.scenarios import ScenarioManager
    paths = ScenarioManager.write_run_scripts(str(tmp_path), ["A"], "fds", num_processes=4)
    assert 'mpiexec -n 4 "%FDS%" A.fds' in open(paths["bat"]).read()
    with pytest.raises(ValueError):
        ScenarioManager.write_run_scripts(str(tmp_path), ["A"], "fds", num_processes=0)


def test_no_scenarios_writes_no_scripts(api, tmp_path):
    assert api.scenarios.export_all(str(tmp_path)) == {}
    assert not (tmp_path / "run_all.bat").exists()


# ---------------------------------------------------------------- CHK-01
def test_checks_list_has_descriptions_and_toggle_is_undoable(api):
    checks = api.validation.checks()
    assert len(checks) >= 25 and all(c["description"] for c in checks)
    assert all(c["enabled"] for c in checks)
    api.validation.set_enabled("MeshPresence", False)
    assert api.project.disabled_checks == ["MeshPresence"]
    assert [c["enabled"] for c in api.validation.checks() if c["name"] == "MeshPresence"] == [False]
    api.history.undo()
    assert api.project.disabled_checks == []
    with pytest.raises(KeyError):
        api.validation.set_enabled("NoSuchCheck", False)


def test_disabled_check_is_skipped_everywhere(api):
    api.meshes.clear()
    assert any(r.rule == "MeshPresence" for r in api.validation.validate().results)
    api.validation.set_enabled("MeshPresence", False)
    assert not any(r.rule == "MeshPresence" for r in api.validation.validate().results)


def test_disabled_checks_are_saved_with_the_project(api, tmp_path):
    api.validation.set_enabled_many({"MeshPresence": False, "DuplicateId": False})
    api.history.undo()                                            # many = one step
    assert api.project.disabled_checks == []
    api.validation.set_enabled_many({"MeshPresence": False, "DuplicateId": False})
    path = tmp_path / "p.pyfds"
    Serializer().save(api.project, str(path))
    assert sorted(Serializer().load(str(path)).disabled_checks) == ["DuplicateId", "MeshPresence"]


def test_share_check_set_roundtrip_and_unknown_names(api, tmp_path):
    api.validation.set_enabled("DuplicateId", False)
    f = api.validation.export_check_set(str(tmp_path / "team.json"), name="team")
    assert json.load(open(f))["disabled"] == ["DuplicateId"]
    other = FdsApi()
    assert other.validation.import_check_set(f) == []
    assert other.project.disabled_checks == ["DuplicateId"]
    data = json.load(open(f))
    data["disabled"] += ["FutureRule"]
    (tmp_path / "newer.json").write_text(json.dumps(data))
    assert other.validation.import_check_set(str(tmp_path / "newer.json")) == ["FutureRule"]
    (tmp_path / "bad.json").write_text('{"format": "other"}')
    with pytest.raises(ValueError, match="not a PyFDS check set"):
        other.validation.import_check_set(str(tmp_path / "bad.json"))


# ---------------------------------------------------------------- gate
def test_gate_blocks_on_errors_not_warnings(api):
    api.validation.gate()                                          # clean model passes
    assert api.validation.can_run()
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], surf_id="MISSING_SURF", name="Bad")
    report_errors = api.validation.validate().errors
    assert report_errors
    with pytest.raises(ValidationGateError) as exc:
        api.validation.gate()
    assert exc.value.report.errors and "validation errors" in str(exc.value)
    assert not api.validation.can_run()


def test_run_pipeline_refuses_an_invalid_model(api, tmp_path):
    api.meshes.clear()                                             # MeshPresence = error
    result = api.execution.run(output_dir=str(tmp_path), validate_first=True)
    assert not result.success and "Validation failed" in (result.error or "")


def test_gate_respects_disabled_checks(api):
    api.meshes.clear()
    with pytest.raises(ValidationGateError):
        api.validation.gate()
    api.validation.set_enabled("MeshPresence", False)
    api.validation.gate()


# ---------------------------------------------------------------- CHK-03
def test_locate_finds_the_entity_for_click_through(api):
    api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], surf_id="MISSING_SURF", name="Bad")
    hit = next(r for r in api.validation.validate().results if r.entity_name == "Bad")
    assert api.validation.locate(hit) is api.obstructions.get("Bad")
    from pyfds.validation.engine import ValidationResult, Severity
    assert api.validation.locate(ValidationResult(Severity.INFO, "x", "no entity")) is None
    assert api.validation.locate(ValidationResult(Severity.INFO, "x", "gone", entity_name="Nope")) is None


# ---------------------------------------------------------------- CHK-05
def test_live_checking_follows_edits_undo_and_redo(api):
    seen = []
    api.validation.watch(seen.append)
    try:
        assert api.validation.watching and api.validation.live_report is None
        api.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], surf_id="MISSING_SURF", name="Bad")
        assert api.validation.live_report.errors
        n = len(seen)
        api.history.undo()
        assert not api.validation.live_report.errors and len(seen) == n + 1
        api.history.redo()
        assert api.validation.live_report.errors
    finally:
        api.validation.unwatch()
    count = len(seen)
    api.history.undo()
    assert len(seen) == count and not api.validation.watching        # stopped


def test_live_checking_throttle(api):
    seen = []
    api.validation.watch(seen.append, min_interval=3600)
    try:
        api.obstructions.add_obstruction(xb=[0, 0.1, 0, 0.1, 0, 0.1], name="A")
        api.obstructions.add_obstruction(xb=[0.2, 0.3, 0, 0.1, 0, 0.1], name="B")
        assert len(seen) == 1
    finally:
        api.validation.unwatch()


# ---------------------------------------------------------------- agent tools
def test_agent_tools_for_checks(api, tmp_path):
    d = AgentToolDispatcher(api)
    assert any(c["name"] == "MeshPresence" for c in d.call("list_model_checks", {}))
    d.call("set_model_check_enabled", {"name": "MeshPresence", "enabled": False})
    f = d.call("export_check_set", {"filepath": str(tmp_path / "s.json")})
    d.call("set_model_check_enabled", {"name": "MeshPresence", "enabled": True})
    assert d.call("import_check_set", {"filepath": f}) == []
    assert api.project.disabled_checks == ["MeshPresence"]
