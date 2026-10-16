"""F1: merging files into the open project, scenario definition files, configuration files (File > Import / Export)."""
import json

import pytest

from pyfds.api import FdsApi
from pyfds.io.serializer import Serializer


@pytest.fixture
def source(tmp_path):
    """A small model saved both as .fds and .pyfds."""
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 2, 0, 2, 0, 2], name="SRC_MESH")
    a.materials.create_default("WOOL")
    a.devices.add_device("TEMPERATURE", [1, 1, 1], name="TC1")
    a.controls.add_control("ANY", ["TC1"], name="ALARM")
    a.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="BOX")
    fds, pyfds = tmp_path / "src.fds", tmp_path / "src.pyfds"
    fds.write_text(a.fds_text())
    Serializer().save(a.project, str(pyfds))
    return {"fds": str(fds), "pyfds": str(pyfds)}


# -- merge_file --------------------------------------------------------------------------------------------------------
def test_merge_everything_from_an_fds_file_in_one_undo_step(source):
    api = FdsApi()
    r = api.clipboard.merge_file(source["fds"])
    assert {e.name for e in r["added"]} >= {"SRC_MESH", "WOOL", "TC1", "ALARM", "BOX"}
    assert api.meshes.get("SRC_MESH") is not None and api.obstructions.get("BOX") is not None
    api.history.undo()
    assert api.meshes.all() == [] and api.devices.all() == [] and api.materials.all() == []


def test_merge_only_some_kinds(source):
    api = FdsApi()
    r = api.clipboard.merge_file(source["fds"], categories=["materials"])
    assert [e.name for e in r["added"]] == ["WOOL"] and api.meshes.all() == [] and api.devices.all() == []
    r = api.clipboard.merge_file(source["fds"], categories=["devices", "controls"])
    assert sorted(e.name for e in r["added"]) == ["ALARM", "TC1"]
    with pytest.raises(ValueError, match="of kind ramps"):
        api.clipboard.merge_file(source["fds"], categories=["ramps"])             # nothing of that kind in the file


def test_merge_reuses_shared_definitions_and_renames_the_rest(source):
    api = FdsApi()
    api.materials.create_default("WOOL")
    api.obstructions.add_obstruction([5, 6, 5, 6, 0, 1], name="BOX")
    r = api.clipboard.merge_file(source["fds"])
    assert "materials/WOOL" in r["skipped"]                                       # a material is reused, not duplicated
    assert len(api.materials.all()) == 1
    assert r["renamed"].get("BOX") == "BOX_2" and api.obstructions.get("BOX_2") is not None


def test_merge_with_an_offset_moves_the_objects(source):
    api = FdsApi()
    api.clipboard.merge_file(source["fds"], categories=["obstructions"], offset=(10, 0, 0))
    box = api.obstructions.get("BOX")
    assert (box.x_min, box.x_max) == (10, 11)


def test_merge_a_pyfds_project_file(source):
    api = FdsApi()
    r = api.clipboard.merge_file(source["pyfds"], categories=["meshes", "obstructions"])
    assert sorted(e.name for e in r["added"]) == ["BOX", "SRC_MESH"]


def test_merge_refuses_missing_and_unreadable_files(tmp_path):
    api = FdsApi()
    with pytest.raises(FileNotFoundError):
        api.clipboard.merge_file(str(tmp_path / "nope.fds"))
    junk = tmp_path / "junk.pyfds"
    junk.write_text("not json at all")
    with pytest.raises(ValueError, match="cannot read"):
        api.clipboard.merge_file(str(junk))
    empty = tmp_path / "empty.fds"
    empty.write_text("! nothing here\n")
    with pytest.raises(ValueError, match="no FDS objects"):
        api.clipboard.merge_file(str(empty))
    assert api.meshes.all() == []


# -- scenario definitions ---------------------------------------------------------------------------------------------------
def _model():
    a = FdsApi()
    a.meshes.add_mesh([10, 10, 10], [0, 4, 0, 4, 0, 3], name="M")
    a.obstructions.add_obstruction([1, 2, 1, 2, 0, 1], name="TABLE")
    return a


def test_scenario_definitions_round_trip_between_models(tmp_path):
    a = _model()
    a.scenarios.create("wide", "a wider room")
    a.scenarios.update("wide", tags=["geometry"])
    a.scenarios.set_override("wide", a.meshes.get("M"), "x_max", 6.0)
    a.scenarios.set_override("wide", a.obstructions.get("TABLE"), "enabled", False)
    a.scenarios.create("empty")
    f = tmp_path / "defs.json"
    assert a.scenarios.export_definitions(str(f)) == 2
    b = _model()                                                                # a different object with the same names
    r = b.scenarios.import_definitions(str(f))
    assert sorted(r["added"]) == ["empty", "wide"] and r["missing"] == []
    wide = b.scenarios.get("wide")
    assert wide.description == "a wider room" and wide.tags == ["geometry"] and wide.override_count() == 2
    b.scenarios.apply("wide")
    assert b.meshes.get("M").x_max == 6.0 and b.obstructions.get("TABLE").enabled is False
    b.scenarios.reset()
    b.history.undo()                                                            # reset
    b.history.undo()                                                            # apply
    b.history.undo()                                                            # the whole import is one step
    assert b.scenarios.all() == []


def test_import_definitions_reports_missing_objects_and_skips_or_replaces_existing(tmp_path):
    a = _model()
    a.scenarios.create("s")
    a.scenarios.set_override("s", a.meshes.get("M"), "x_max", 9.0)
    f = tmp_path / "d.json"
    a.scenarios.export_definitions(str(f))
    c = FdsApi()                                                                # no mesh named M here
    r = c.scenarios.import_definitions(str(f))
    assert r["added"] == ["s"] and len(r["missing"]) == 1 and "Mesh M" in r["missing"][0]
    assert c.scenarios.get("s").override_count() == 0
    again = c.scenarios.import_definitions(str(f))
    assert again["skipped"] == ["s"] and again["added"] == []
    d = _model()
    assert d.scenarios.import_definitions(str(f), overwrite=True)["added"] == ["s"]
    assert d.scenarios.import_definitions(str(f), overwrite=True)["replaced"] == ["s"]
    d.scenarios.apply("s")
    assert d.scenarios.import_definitions(str(f), overwrite=True)["skipped"] == ["s"]     # the applied one is left alone


def test_import_definitions_refuses_other_files(tmp_path):
    f = tmp_path / "x.json"
    f.write_text(json.dumps({"format": "something-else"}))
    with pytest.raises(ValueError, match="not a PyFDS scenario"):
        FdsApi().scenarios.import_definitions(str(f))
    f.write_text("{{{")
    with pytest.raises(ValueError, match="cannot read"):
        FdsApi().scenarios.import_definitions(str(f))


# -- configuration ---------------------------------------------------------------------------------------------------------------
def test_configuration_export_and_import(tmp_path):
    from pyfds.core.config import get_config
    api = FdsApi()
    keep = {k: get_config().get(k) for k in api.preferences.keys()}
    try:
        api.preferences.set("undo_depth", 77)
        api.preferences.set("auto_save", False)
        api.units.set_system("EN")
        f = tmp_path / "cfg.json"
        assert api.preferences.export_config(str(f)) == len(api.preferences.keys()) + 1
        api.preferences.set("undo_depth", 200)
        api.units.set_system("SI")
        r = api.preferences.import_config(str(f))
        assert api.preferences.get("undo_depth") == 77 and api.preferences.get("auto_save") is False
        assert api.units.system == "EN" and "units" in r["applied"] and r["rejected"] == {}
    finally:
        for k, v in keep.items():
            if v is not None:
                try:
                    api.preferences.set(k, v)
                except (ValueError, KeyError):
                    pass
        api.units.set_system("SI")


def test_import_config_rejects_bad_values_but_applies_the_rest(tmp_path):
    api = FdsApi()
    before = api.preferences.get("undo_depth")
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"format": "pyfds-config", "units": "SI",
                             "preferences": {"undo_depth": 5, "auto_save": True, "colour_of_the_sky": "blue"}}))
    r = api.preferences.import_config(str(f))
    assert "undo_depth" in r["rejected"] and "colour_of_the_sky" in r["rejected"] and "auto_save" in r["applied"]
    assert api.preferences.get("undo_depth") == before                            # 5 is below the allowed minimum
    f.write_text(json.dumps({"format": "other"}))
    with pytest.raises(ValueError, match="not a PyFDS configuration"):
        api.preferences.import_config(str(f))
