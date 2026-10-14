"""B5: FDS-syntax library files and the appearance library."""
from __future__ import annotations

import pytest

from pyfds.api import FdsApi
from pyfds.domain.model import Surface

LIB = """&MATL ID='FOAM', DENSITY=30., CONDUCTIVITY=0.04, SPECIFIC_HEAT=1.5 /
&SURF ID='FOAM WALL', COLOR='YELLOW', MATL_ID='FOAM', THICKNESS=0.05, RAMP_Q='BURN' /
&SURF ID='PLAIN', COLOR='RED' /
&REAC FUEL='METHANE', SOOT_YIELD=0.01 /
&SPEC ID='ARGON' /
&PROP ID='Head', QUANTITY='SPRINKLER LINK TEMPERATURE', ACTIVATION_TEMPERATURE=68., RTI=50. /
&PROP ID='Det', QUANTITY='CHAMBER OBSCURATION', ACTIVATION_OBSCURATION=3.28 /
&RAMP ID='BURN', T=0., F=0. /
&RAMP ID='BURN', T=10., F=1. /
"""


def test_import_fds_sorts_records_into_categories():
    api = FdsApi()
    r = api.library.import_fds("", text=LIB)
    assert "materials/FOAM" in r["added"] and "surfaces/FOAM WALL" in r["added"]
    assert "reactions/REAC" in " ".join(r["added"]) or any(a.startswith("reactions/") for a in r["added"])
    assert "species/ARGON" in r["added"]
    assert "sprinkler_links/Head" in r["added"] or any("Head" in a for a in r["added"])
    assert any(a.startswith("smoke_detectors/") for a in r["added"])
    assert r["missing_ramps"] == ["BURN"] and r["ramps_in_file"] == ["BURN"]
    assert api.library.get("materials", "FOAM")["fields"]["conductivity"] == 0.04


def test_import_fds_respects_overwrite_and_categories():
    api = FdsApi()
    api.library.import_fds("", categories=["materials"], text=LIB)
    assert api.library.names("species", "user") == []
    r = api.library.import_fds("", categories=["materials"], text=LIB)
    assert r["skipped"] == ["materials/FOAM"]
    assert api.library.import_fds("", categories=["materials"], text=LIB, overwrite=True)["replaced"] == ["materials/FOAM"]


def test_fds_round_trip_through_a_file(tmp_path):
    api = FdsApi()
    api.library.import_fds("", text=LIB)
    out = str(tmp_path / "lib.fds")
    n = api.library.export_fds(out, ["materials", "surfaces", "species"])
    assert n == 4
    text = open(out, encoding="utf-8").read()
    assert "&MATL" in text and "&SURF" in text and "FOAM WALL" in text
    other = FdsApi()
    r = other.library.import_fds(out)
    assert "materials/FOAM" in r["added"] and "surfaces/PLAIN" in r["added"]
    assert other.library.get("surfaces", "FOAM WALL")["fields"]["color"] == "YELLOW"


def test_export_fds_can_include_builtins_and_filter(tmp_path):
    api = FdsApi()
    out = str(tmp_path / "b.fds")
    assert api.library.export_fds(out, ["materials"], include_builtin=True, names=["concrete"]) == 1
    assert "&MATL" in open(out, encoding="utf-8").read()


def test_builtin_species_exist():
    api = FdsApi()
    assert "carbon_dioxide" in api.library.names("species", "builtin")
    e = api.library.add_to_model("species", "carbon_dioxide")
    assert e.name == "CARBON_DIOXIDE"


def test_appearances_apply_and_undo():
    api = FdsApi()
    api.surfaces.add(Surface(name="A"))
    api.surfaces.add(Surface(name="B"))
    api.library.add_appearance("water", color="BLUE", rgb=(0, 0, 200), transparency=0.5,
                               texture_map="w.png", texture_width=2.0, texture_height=2.0)
    api.library.apply_appearance("water", ["A", "B"])
    for n in "AB":
        s = api.surfaces.get(n)
        assert s.transparency == 0.5 and s.texture_map == "w.png" and tuple(s.rgb) == (0, 0, 200)
    api.history.undo()
    assert api.surfaces.get("A").transparency == 0.0 and api.surfaces.get("B").texture_map is None


def test_appearance_from_surface_and_validation():
    api = FdsApi()
    api.surfaces.add(Surface(name="S", color="RED", transparency=0.2))
    assert api.library.appearance_from_surface("S") == "S"
    assert api.library.appearance("S")["transparency"] == 0.2
    with pytest.raises(ValueError):
        api.library.appearance_from_surface("S")
    with pytest.raises(ValueError):
        api.library.add_appearance("x", transparency=2)
    with pytest.raises(ValueError):
        api.library.add_appearance("x", rgb=(1, 2, 300))
    with pytest.raises(KeyError):
        api.library.appearance("nope")
    assert "glass" in api.library.appearance_names("builtin")


def test_appearances_survive_library_file(tmp_path):
    api = FdsApi()
    api.library.add_appearance("tile", color="WHITE", texture_map="t.png", texture_width=0.3, rgb=(9, 9, 9))
    f = str(tmp_path / "l.json")
    api.library.export_library(f)
    other = FdsApi()
    r = other.library.import_library(f)
    assert "appearances/tile" in r["added"]
    assert other.library.appearance("tile")["texture_width"] == 0.3
    assert other.library.appearance("tile")["rgb"] == (9, 9, 9)


def test_agent_tools_work():
    from pyfds.agent import AgentToolDispatcher
    d = AgentToolDispatcher(FdsApi())
    assert d.call("appearance_add", {"name": "x", "color": "RED"}) == "x"
    assert d.call("appearance_list", {})["x"]["source"] == "user"
