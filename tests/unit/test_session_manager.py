"""Unit tests — pyfds.api.controller.SessionManager and FdsApi multi-doc."""
from __future__ import annotations

import pytest

from pyfds.api.controller import FdsApi, SessionManager
from pyfds.domain.model import FdsProject


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(chid="default") -> FdsApi:
    p = FdsProject(chid=chid)
    return FdsApi(project=p)


# ---------------------------------------------------------------------------
# SessionManager construction
# ---------------------------------------------------------------------------

class TestSessionManagerConstruction:
    def test_session_attribute_exists(self):
        api = _api()
        assert hasattr(api, "session")
        assert isinstance(api.session, SessionManager)

    def test_initial_project_registered(self):
        api = _api("proj1")
        assert "proj1" in api.session.project_list()

    def test_initial_project_is_active(self):
        api = _api("proj1")
        assert api.session.active_chid == "proj1"

    def test_len_starts_at_one(self):
        assert len(_api().session) == 1


# ---------------------------------------------------------------------------
# api.project property
# ---------------------------------------------------------------------------

class TestProjectProperty:
    def test_api_project_returns_active(self):
        api = _api("alpha")
        assert api.project.chid == "alpha"

    def test_api_project_after_new(self):
        api = _api("alpha")
        api.new(chid="beta")
        assert api.project.chid == "beta"

    def test_api_project_after_switch(self):
        api = _api("alpha")
        api.session.new_project(chid="gamma")
        api.session.switch_project("alpha")
        assert api.project.chid == "alpha"


# ---------------------------------------------------------------------------
# new_project
# ---------------------------------------------------------------------------

class TestNewProject:
    def test_creates_new_project(self):
        api = _api()
        api.session.new_project(chid="new1")
        assert "new1" in api.session.project_list()

    def test_activates_new_project(self):
        api = _api("original")
        api.session.new_project(chid="fresh")
        assert api.session.active_chid == "fresh"

    def test_api_project_reflects_new(self):
        api = _api("original")
        api.session.new_project(chid="fresh")
        assert api.project.chid == "fresh"

    def test_len_increases(self):
        api = _api()
        api.session.new_project(chid="x")
        assert len(api.session) == 2

    def test_title_applied(self):
        api = _api()
        p = api.session.new_project(chid="titled", title="My Title")
        assert p.title == "My Title"

    def test_returns_fds_project(self):
        api = _api()
        p = api.session.new_project(chid="ret")
        assert isinstance(p, FdsProject)


# ---------------------------------------------------------------------------
# api.new() delegation
# ---------------------------------------------------------------------------

class TestApiNew:
    def test_new_changes_project(self):
        api = _api("old")
        old_id = id(api.project)
        api.new(chid="new_case")
        assert id(api.project) != old_id

    def test_new_updates_chid(self):
        api = _api("old")
        api.new(chid="new_case")
        assert api.project.chid == "new_case"

    def test_new_registers_in_session(self):
        api = _api("old")
        api.new(chid="brand_new")
        assert "brand_new" in api.session.project_list()


# ---------------------------------------------------------------------------
# switch_project
# ---------------------------------------------------------------------------

class TestSwitchProject:
    def test_switch_changes_active(self):
        api = _api("a")
        api.session.new_project(chid="b")
        api.session.switch_project("a")
        assert api.session.active_chid == "a"

    def test_switch_updates_api_project(self):
        api = _api("a")
        api.session.new_project(chid="b")
        api.session.switch_project("a")
        assert api.project.chid == "a"

    def test_switch_to_unknown_raises_key_error(self):
        api = _api()
        with pytest.raises(KeyError):
            api.session.switch_project("doesnotexist")

    def test_switch_returns_project(self):
        api = _api("p1")
        api.session.new_project(chid="p2")
        p = api.session.switch_project("p1")
        assert isinstance(p, FdsProject)
        assert p.chid == "p1"


# ---------------------------------------------------------------------------
# close_project
# ---------------------------------------------------------------------------

class TestCloseProject:
    def test_close_removes_project(self):
        api = _api("a")
        api.session.new_project(chid="b")
        api.session.close_project("b")
        assert "b" not in api.session.project_list()

    def test_close_active_switches_to_other(self):
        api = _api("a")
        api.session.new_project(chid="b")
        api.session.close_project("a")
        assert api.session.active_chid == "b"
        assert api.project.chid == "b"

    def test_close_last_project_raises(self):
        api = _api("only")
        with pytest.raises(RuntimeError):
            api.session.close_project("only")

    def test_close_unknown_raises_key_error(self):
        api = _api()
        with pytest.raises(KeyError):
            api.session.close_project("ghost")

    def test_len_decreases_after_close(self):
        api = _api("a")
        api.session.new_project(chid="b")
        api.session.close_project("b")
        assert len(api.session) == 1


# ---------------------------------------------------------------------------
# project_list and get_project
# ---------------------------------------------------------------------------

class TestProjectList:
    def test_lists_all_chids(self):
        api = _api("p1")
        api.session.new_project("p2")
        api.session.new_project("p3")
        lst = api.session.project_list()
        assert set(lst) == {"p1", "p2", "p3"}

    def test_get_project_by_chid(self):
        api = _api("main")
        api.session.new_project("sub")
        p = api.session.get_project("sub")
        assert p is not None
        assert p.chid == "sub"

    def test_get_project_unknown_returns_none(self):
        api = _api()
        assert api.session.get_project("ghost") is None


# ---------------------------------------------------------------------------
# open_project and save_project
# ---------------------------------------------------------------------------

class TestOpenSaveProject:
    def test_open_pyfds_file(self, tmp_path):
        from pyfds.io.serializer import Serializer
        p = FdsProject(chid="saved_case", title="Test")
        pyfds_path = str(tmp_path / "saved_case.pyfds")
        Serializer().save(p, pyfds_path)

        api = _api("other")
        opened = api.session.open_project(pyfds_path)
        assert opened.chid == "saved_case"
        assert api.session.active_chid == "saved_case"

    def test_open_unsupported_format_raises(self, tmp_path):
        bad = tmp_path / "bad.txt"
        bad.write_text("nothing")
        api = _api()
        with pytest.raises(ValueError):
            api.session.open_project(str(bad))

    def test_save_active_project(self, tmp_path):
        api = _api("tosave")
        pyfds_path = str(tmp_path / "tosave.pyfds")
        api.session.save_project(pyfds_path)
        assert (tmp_path / "tosave.pyfds").exists()

    def test_save_specific_project(self, tmp_path):
        api = _api("a")
        api.session.new_project("b")
        pyfds_path = str(tmp_path / "b.pyfds")
        api.session.save_project(pyfds_path, chid="b")
        assert (tmp_path / "b.pyfds").exists()


# ---------------------------------------------------------------------------
# Entity persistence across project switches
# ---------------------------------------------------------------------------

class TestEntityPersistence:
    def test_entities_survive_project_switch(self):
        from pyfds.domain.model import Mesh
        api = _api("scene1")
        m = Mesh(name="wall_mesh", cell_count=(10, 10, 5),
                 x_min=0, x_max=10, y_min=0, y_max=10, z_min=0, z_max=5)
        api.project.add_entity(m)

        api.session.new_project("scene2")
        assert len(api.project.meshes) == 0   # scene2 is empty

        api.session.switch_project("scene1")
        assert len(api.project.meshes) == 1
        assert api.project.meshes[0].name == "wall_mesh"

    def test_modifications_in_one_project_dont_bleed(self):
        from pyfds.domain.model import Surface
        api = _api("proj_a")
        api.project.add_entity(Surface(name="FIRE"))

        api.session.new_project("proj_b")
        api.project.add_entity(Surface(name="CONCRETE"))

        api.session.switch_project("proj_a")
        names = [s.name for s in api.project.surfaces]
        assert "FIRE" in names
        assert "CONCRETE" not in names


# ---------------------------------------------------------------------------
# Round-trip serialization fidelity
# ---------------------------------------------------------------------------

class TestSerializationFidelity:
    def test_entities_round_trip_through_pyfds_file(self, tmp_path):
        from pyfds.io.serializer import Serializer
        from pyfds.domain.model import Mesh

        p = FdsProject(chid="fidelity", title="Fidelity Test")
        p.add_entity(Mesh(name="main_mesh", cell_count=(20, 20, 10),
                          x_min=0, x_max=4, y_min=0, y_max=4,
                          z_min=0, z_max=2))
        path = str(tmp_path / "fidelity.pyfds")
        Serializer().save(p, path)

        api = _api("other")
        opened = api.session.open_project(path)
        assert opened.title == "Fidelity Test"
        assert len(opened.meshes) == 1
        assert opened.meshes[0].name == "main_mesh"

    def test_unsupported_format_error_mentions_extension(self, tmp_path):
        bad = tmp_path / "data.xyz"
        bad.write_text("nothing useful")
        api = _api()
        with pytest.raises(ValueError) as exc_info:
            api.session.open_project(str(bad))
        assert ".xyz" in str(exc_info.value) or "xyz" in str(exc_info.value).lower() or "unsupported" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Manager rebind after switch
# ---------------------------------------------------------------------------

class TestManagerRebind:
    def test_obstructions_manager_sees_active_project(self):
        from pyfds.domain.model import Obstruction
        api = _api("scene1")
        from pyfds.automation.commands import AddEntityCommand
        o = Obstruction(name="wall1",
                        x_min=0, x_max=1, y_min=0, y_max=1, z_min=0, z_max=1)
        api.history.execute(AddEntityCommand(api.project, o))

        api.session.new_project("scene2")
        # scene2 should have no obstructions
        assert api.obstructions.count() == 0

        api.session.switch_project("scene1")
        # Back to scene1: should see the wall
        assert api.obstructions.count() == 1

    def test_repr_contains_active_chid(self):
        api = _api("myproj")
        r = repr(api.session)
        assert "myproj" in r
