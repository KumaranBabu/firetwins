"""G3 — species, zones, props, mults, moves, mesh transforms, text blocks are authorable.

Every mutation is one undo step, reachable through the API *and* the agent tool
registry, and survives the FDS write -> parse round trip.
"""
from __future__ import annotations

import pytest

from pyfds.agent import AgentToolDispatcher
from pyfds.api import FdsApi
from pyfds.io.fds_parser import FdsParser
from pyfds.io.fds_writer import FdsWriter


@pytest.fixture
def api():
    a = FdsApi()
    a.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1))
    return a


def _undo_redo(api, manager, before, after):
    assert manager.count() == after
    api.history.undo()
    assert manager.count() == before
    api.history.redo()
    assert manager.count() == after


# ---------------------------------------------------------------- species
def test_species_add_lumped_background_and_guards(api):
    api.species.add_species("OXYGEN", 32.0)
    api.species.add_species("NITROGEN", 28.0)
    _undo_redo(api, api.species, 1, 2)
    air = api.species.add_lumped("AIR", ["OXYGEN", "NITROGEN"], volume_fractions=[0.21, 0.79])
    assert air.primitive is False and air.spec_id == ["OXYGEN", "NITROGEN"]

    with pytest.raises(ValueError, match="already exists"):
        api.species.add_species("OXYGEN")
    with pytest.raises(ValueError, match="unknown component"):
        api.species.add_lumped("X", ["NOPE"], volume_fractions=[1.0])
    with pytest.raises(ValueError, match="one per component"):
        api.species.add_lumped("X", ["OXYGEN"], volume_fractions=[0.5, 0.5])

    api.species.set_background("NITROGEN")
    assert [s.name for s in api.species.all() if s.background] == ["NITROGEN"]
    api.species.set_background("OXYGEN")
    assert [s.name for s in api.species.all() if s.background] == ["OXYGEN"]
    api.history.undo()                                   # whole switch = one step
    assert [s.name for s in api.species.all() if s.background] == ["NITROGEN"]


def test_species_remove_checked_refuses_when_referenced(api):
    api.species.add_species("OXYGEN", 32.0)
    api.species.add_lumped("AIR", ["OXYGEN"], volume_fractions=[1.0])
    with pytest.raises(ValueError, match="used by"):
        api.species.remove_checked("OXYGEN")
    api.species.remove_checked("AIR")
    api.species.remove_checked("OXYGEN")
    assert api.species.count() == 0


def test_update_and_rename_are_one_undo_step_and_reject_typos(api):
    sp = api.species.add_species("OXYGEN", 32.0)
    api.species.update("OXYGEN", mw=31.9, formula="O2")
    assert (sp.mw, sp.formula) == (31.9, "O2")
    api.history.undo()
    assert (sp.mw, sp.formula) == (32.0, None)
    with pytest.raises(AttributeError, match="no field"):
        api.species.update("OXYGEN", mww=1.0)
    assert sp.mw == 32.0                                  # nothing half-applied
    api.species.rename("OXYGEN", "O2_GAS")
    assert api.species.get("O2_GAS") is sp
    with pytest.raises(KeyError):
        api.species.update("MISSING", mw=1.0)


# ------------------------------------------------------------------ zones
def test_zone_add_auto_name_edit_and_undo(api):
    z1 = api.zones.add_zone([0.5, 0.5, 0.5])
    z2 = api.zones.add_zone([0.2, 0.2, 0.2])
    assert (z1.name, z2.name) == ("ZONE", "ZONE_2")
    _undo_redo(api, api.zones, 1, 2)
    api.zones.set_leak_areas("ZONE", [0.01, 0.02])
    assert z1.leak_areas == [0.01, 0.02]
    with pytest.raises(ValueError):
        api.zones.add_zone([0, 0])
    with pytest.raises(ValueError, match="already exists"):
        api.zones.add_zone([0, 0, 0], name="ZONE")


# ------------------------------------------------------- props/mults/etc.
def test_props_mults_moves_transforms_texts(api):
    api.props.add_sprinkler("SPK", rti=100.0)
    api.props.add_smoke_detector("SD")
    assert api.props.get("SPK").rti == 100.0
    assert api.props.get("SD").activation_obscuration == 3.28

    m = api.mults.add_mult("ROW", dx=2.0, i=(0, 4), k=(0, 1))
    assert api.mults.copies(m) == 10
    with pytest.raises(ValueError):
        api.mults.add_mult("BAD", i=(3, 1))

    api.moves.add_translation(1, 2, 3, name="SHIFT")
    rot = api.moves.add_rotation(45, origin=(1, 1, 0), name="TURN")
    assert (rot.rotation_angle, rot.x0, rot.y0) == (45, 1, 1)

    t = api.mesh_transforms.add_transform("x", cc=0.5, pc=0.25)
    assert (t.direction, t.name) == ("X", "TRNX")
    with pytest.raises(ValueError):
        api.mesh_transforms.add_transform("W", cc=0)
    with pytest.raises(ValueError):
        api.mesh_transforms.add_transform("Y", cc=0, pc=1.5)

    txt = api.texts.add_text("&MISC TMPA=25 /")
    assert api.texts.get(0) is txt and api.texts.get(5) is None

    # history is LIFO: undo in reverse creation order, one step per add
    for mgr, left in ((api.texts, 0), (api.mesh_transforms, 0), (api.moves, 1), (api.moves, 0),
                      (api.mults, 0), (api.props, 1), (api.props, 0)):
        api.history.undo()
        assert mgr.count() == left


# ------------------------------------------------------ agent tool registry
def test_agent_tools_cover_every_g3_entity(api):
    d = AgentToolDispatcher(api)
    d.call("add_species", {"name": "OXYGEN", "mw": 32.0})
    d.call("add_species", {"name": "NITROGEN", "mw": 28.0, "background": True})
    d.call("add_lumped_species", {"name": "AIR", "components": ["OXYGEN", "NITROGEN"],
                                  "volume_fractions": [0.21, 0.79]})
    d.call("edit_species", {"name": "OXYGEN", "fields": {"mw": 31.9}})
    d.call("add_zone", {"xyz": [0.5, 0.5, 0.5], "name": "Z1"})
    d.call("edit_zone", {"name": "Z1", "fields": {"leak_areas": [0.1, 0.1]}})
    d.call("add_sprinkler_prop", {"name": "SPK"})
    d.call("add_smoke_detector_prop", {"name": "SD"})
    d.call("add_mult", {"name": "M", "dx": 1.0, "i": [0, 2]})
    d.call("add_translation", {"name": "T", "dx": 1.0})
    d.call("add_rotation", {"angle": 30.0, "name": "R"})
    d.call("add_mesh_transform", {"direction": "Z", "cc": 0.5})
    d.call("add_text_block", {"content": "&MISC TMPA=20 /"})

    assert [s["name"] for s in d.call("list_species", {})] == ["OXYGEN", "NITROGEN", "AIR"]
    assert api.species.get("OXYGEN").mw == 31.9
    for tool, n in (("list_zones", 1), ("list_props", 2), ("list_mults", 1), ("list_moves", 2),
                    ("list_mesh_transforms", 1), ("list_text_blocks", 1)):
        assert len(d.call(tool, {})) == n, tool

    with pytest.raises(Exception):
        d.call("remove_species", {"name": "OXYGEN"})      # still used by AIR
    for tool, args in (("remove_species", {"name": "AIR"}), ("remove_zone", {"name": "Z1"}),
                       ("remove_prop", {"name": "SPK"}), ("remove_mult", {"name": "M"}),
                       ("remove_move", {"name": "T"}), ("remove_text_block", {"index": 0})):
        d.call(tool, args)
    assert api.species.count() == 2 and api.zones.count() == 0 and api.texts.count() == 0


# ------------------------------------------------------ FDS round trip
def test_authored_entities_survive_write_parse(api, tmp_path):
    api.species.add_species("OXYGEN", 32.0)
    api.species.add_species("NITROGEN", 28.0)
    api.species.add_lumped("AIR", ["OXYGEN", "NITROGEN"], volume_fractions=[0.21, 0.79])
    api.zones.add_zone([0.5, 0.5, 0.5], name="Z1")
    api.props.add_sprinkler("SPK", rti=80.0)
    api.mults.add_mult("ROW", dx=0.2, i=(0, 3))
    api.mesh_transforms.add_transform("X", cc=0.5, pc=0.5)
    out = tmp_path / "g3.fds"
    FdsWriter().write(api.project, str(out))
    text = out.read_text()
    for token in ("&SPEC", "&ZONE", "&PROP", "&MULT", "&TRNX"):
        assert token in text, token
    back = FdsParser().parse(str(out))
    assert {s.name for s in back.species} >= {"OXYGEN", "NITROGEN", "AIR"}
    assert [z.name for z in back.zones] == ["Z1"]
    assert back.props[0].rti == 80.0
    assert back.mults[0].i_upper == 3
    assert len(back.mesh_transforms) == 1


def test_legacy_module_is_gone_and_hvac_solver_kept(api):
    with pytest.raises(ImportError):
        import pyfds.api.legacy  # noqa: F401
    assert callable(api.hvac.solve_network) and callable(api.config.configure_simulation)
    for gone in ("geometry", "physics", "network", "output", "runner"):
        assert not hasattr(api, gone), gone
