"""P0 partial rows, batch 2: unified library model (LIB-01) and material library import (MAT-05)."""
from __future__ import annotations

import json

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.domain import libraries as lib


@pytest.fixture
def api():
    return FdsApi()


def test_all_nine_categories_present(api):
    keys = [c["key"] for c in api.library.categories()]
    assert keys == ["reactions", "heat_detectors", "materials", "particles", "smoke_detectors", "species",
                    "spray_models", "sprinkler_links", "surfaces"]
    counts = {c["key"]: c["builtin"] for c in api.library.categories()}
    assert counts["materials"] > 10 and counts["surfaces"] > 3 and counts["reactions"] >= 20
    assert counts["heat_detectors"] and counts["smoke_detectors"] and counts["sprinkler_links"]


def test_unknown_category_and_entry(api):
    with pytest.raises(KeyError):
        api.library.names("nonsense")
    with pytest.raises(KeyError):
        api.library.get("materials", "unobtainium")
    with pytest.raises(ValueError):
        api.library.names("materials", "everything")


def test_add_builtin_material_to_model_is_undoable(api):
    m = api.library.add_to_model("materials", "concrete")
    assert m.name == "CONCRETE" and m.density > 1000
    assert api.materials.get("CONCRETE") is m
    api.history.undo()
    assert api.materials.get("CONCRETE") is None


def test_add_surface_brings_its_materials_in_one_step(api):
    s = api.library.add_to_model("surfaces", "gypsum_wall_25mm")
    need = {l.material_id for l in s.layers}
    assert need <= {m.name for m in api.project.materials}
    api.history.undo()
    assert not api.project.materials and not api.project.surfaces


def test_duplicate_is_refused_unless_renamed(api):
    api.library.add_to_model("materials", "concrete")
    with pytest.raises(ValueError):
        api.library.add_to_model("materials", "concrete")
    assert api.library.add_to_model("materials", "concrete", "CONCRETE_B").name == "CONCRETE_B"


def test_reaction_from_library(api):
    r = api.library.add_to_model("reactions", "propane")
    assert r.fuel == "PROPANE" and r.heat_of_combustion > 40000


def test_detector_and_sprinkler_entries_go_to_the_right_category(api):
    p = api.library.add_to_model("sprinkler_links", "sprinkler_quick_68C")
    assert p.rti == 50.0 and p.activation_temperature == 68.0
    h = api.library.add_to_model("heat_detectors", "heat_detector_74C")
    s = api.library.add_to_model("smoke_detectors", "smoke_detector_generic")
    api.library.add_to_library("heat_detectors", h, name="mine")
    with pytest.raises(ValueError):
        api.library.add_to_library("smoke_detectors", h)         # a heat detector is not a smoke detector
    api.library.add_to_library("smoke_detectors", s, name="mine_smoke")
    assert api.library.names("heat_detectors", "user") == ["mine"]
    assert api.library.names("smoke_detectors", "user") == ["mine_smoke"]
    assert api.library.names("sprinkler_links", "user") == []


def test_add_to_library_and_back(api):
    from pyfds.domain.model import Material
    api.materials.add(Material(name="MY_FOAM", density=30.0, conductivity=0.04, specific_heat=1.4))
    assert api.library.add_to_library("materials", "MY_FOAM", description="foam") == "MY_FOAM"
    e = api.library.get("materials", "MY_FOAM")
    assert e["source"] == "user" and e["fields"]["density"] == 30.0 and "name" not in e["fields"]
    with pytest.raises(ValueError):
        api.library.add_to_library("materials", "MY_FOAM")
    api.library.add_to_library("materials", "MY_FOAM", overwrite=True)
    api2 = FdsApi()
    api2._lib_check = True
    path_api = api.library
    got = path_api.add_to_model("materials", "MY_FOAM", "FOAM2")
    assert got.density == 30.0 and got.conductivity == 0.04
    with pytest.raises(KeyError):
        api.library.add_to_library("materials", "NOPE")


def test_user_entry_shadows_builtin_and_only_user_can_be_removed(api):
    from pyfds.domain.model import Material
    api.materials.add(Material(name="x", density=1.0))
    api.library.add_to_library("materials", "x", name="concrete")
    assert api.library.get("materials", "concrete")["source"] == "user"
    api.library.remove_from_library("materials", "concrete")
    assert api.library.get("materials", "concrete")["source"] == "builtin"
    with pytest.raises(KeyError):
        api.library.remove_from_library("materials", "concrete")


def test_export_import_round_trip_between_projects(api, tmp_path):
    from pyfds.domain.model import Material
    api.materials.add(Material(name="A", density=11.0))
    api.materials.add(Material(name="B", density=22.0))
    api.library.add_to_library("materials", "A")
    api.library.add_to_library("materials", "B")
    f = str(tmp_path / "lib.json")
    assert api.library.export_library(f) == 2
    other = FdsApi()
    rep = other.library.import_library(f)
    assert sorted(rep["added"]) == ["materials/A", "materials/B"] and not rep["invalid"]
    assert other.library.add_to_model("materials", "B").density == 22.0
    again = other.library.import_library(f)
    assert len(again["skipped"]) == 2
    assert len(other.library.import_library(f, overwrite=True)["replaced"]) == 2


def test_export_with_builtin(api, tmp_path):
    f = str(tmp_path / "all.json")
    n = api.library.export_library(f, ["reactions"], include_builtin=True)
    assert n >= 20
    assert json.load(open(f))["format"] == "pyfds-library"


def test_import_reports_bad_entries_and_rejects_bad_files(api, tmp_path):
    good = tmp_path / "g.json"
    good.write_text(json.dumps(lib.to_document({
        "materials": {"OK": {"fields": {"density": 5.0}}, "BAD": {"fields": {"density": "heavy"}},
                      "NOFIELDS": {"density": 1}},
        "wibble": {"X": {"fields": {}}}})))
    rep = api.library.import_library(str(good))
    assert rep["added"] == ["materials/OK"] and len(rep["invalid"]) == 3
    for text in ("not json", json.dumps({"format": "other"}), json.dumps({"format": "pyfds-library", "version": 99,
                                                                          "categories": {}})):
        f = tmp_path / "b.json"
        f.write_text(text)
        with pytest.raises(ValueError):
            api.library.import_library(str(f))
    assert api.library.names("materials", "user") == ["OK"]


def test_import_database_tables_from_export(api, tmp_path):
    for fmt in ("json", "csv"):
        f = str(tmp_path / f"m.{fmt}")
        api.engineering.export_materials(f, fmt=fmt)
        fresh = FdsApi()
        rep = fresh.library.import_table("materials", f)
        assert len(rep["added"]) > 10 and not rep["invalid"], (fmt, rep["invalid"][:2])
        assert fresh.library.get("materials", "concrete")["fields"]["density"] == pytest.approx(2280.0)


def test_persistence_with_path(api, tmp_path):
    from pyfds.domain.model import Material
    api.library.path = str(tmp_path / "user.json")
    api.materials.add(Material(name="P", density=9.0))
    api.library.add_to_library("materials", "P")
    assert (tmp_path / "user.json").exists()
    other = FdsApi()
    other.library.path = api.library.path
    other.library.load()
    assert other.library.names("materials", "user") == ["P"]
    other.library.path = str(tmp_path / "missing.json")
    assert other.library.load()["added"] == []
    with pytest.raises(ValueError):
        FdsApi().library.save()


def test_agent_tools(api, tmp_path):
    d = AgentToolDispatcher(api)
    assert len(d.call("library_categories", {})) == 9
    assert "concrete" in d.call("library_entries", {"category": "materials", "source": "builtin"})
    assert d.call("library_entry", {"category": "materials", "name": "concrete"})["source"] == "builtin"
    assert d.call("library_add_to_model", {"category": "materials", "name": "concrete"}) == "CONCRETE"
    assert d.call("library_add_to_library", {"category": "materials", "entity": "CONCRETE", "name": "c2"}) == "c2"
    f = str(tmp_path / "t.json")
    assert d.call("library_export", {"filepath": f}) == 1
    assert d.call("library_import", {"filepath": f, "overwrite": True})["replaced"] == ["materials/c2"]
    d.call("library_remove", {"category": "materials", "name": "c2"})
    assert api.library.names("materials", "user") == []
