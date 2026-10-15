"""B8: write protection, backup on open, autosave recovery, remove all objects, bulk rename,
preferences, curated examples, new-model defaults."""
import os
import time

import pytest

from pyfds.api import FdsApi
from pyfds.api.examples import _EXAMPLES
from pyfds.core.config import get_config
from pyfds.core.exceptions import FdsSerializationError
from pyfds.domain.model import Surface
from pyfds.io import recovery
from pyfds.io.fds_writer import FdsWriter
from pyfds.io.serializer import Serializer


@pytest.fixture
def api():
    return FdsApi()


@pytest.fixture
def restore_prefs():
    cfg = get_config()
    saved = {k: cfg.get(k) for k in ("undo_depth", "create_backup_on_open", "recent_files_max")}
    yield
    for k, v in saved.items():
        cfg.set(k, v)


# -- write protection ---------------------------------------------------------------------
def test_write_protection_blocks_save_over_opened_file(api, tmp_path):
    path = tmp_path / "m.pyfds"
    api.save(str(path))
    api.load(str(path))
    api.hygiene.set_write_protection(True)
    with pytest.raises(FdsSerializationError, match="write protected"):
        api.save(str(path))
    other = tmp_path / "copy.pyfds"
    api.save(str(other))                              # Save As: an ordinary, unprotected copy
    assert not api.hygiene.write_protected
    api.save(str(other))                              # and it can be saved over


def test_write_protection_travels_with_the_file(api, tmp_path):
    path = tmp_path / "m.pyfds"
    api.hygiene.set_write_protection(True)
    api.save(str(path))                               # never opened from here, so allowed
    api2 = FdsApi()
    api2.load(str(path))
    assert api2.hygiene.write_protected
    with pytest.raises(FdsSerializationError):
        api2.save(str(path))


# -- backup and recovery ---------------------------------------------------------------------
def test_backup_on_open_keeps_the_file_as_opened(api, tmp_path, restore_prefs):
    path = tmp_path / "m.pyfds"
    api.project.title = "first"
    api.save(str(path))
    api.load(str(path))
    backup = recovery.backup_path(path)
    assert backup.is_file() and api.hygiene.backup_file(str(path)) == str(backup)
    api.project.title = "second"
    api.save(str(path))
    api.hygiene.restore_backup(str(path))
    assert api.project.title == "first"
    get_config().set("create_backup_on_open", False)
    other = tmp_path / "n.pyfds"
    api.save(str(other))
    api.load(str(other))
    assert not recovery.backup_path(other).exists()


def test_autosave_never_touches_the_real_file_and_recovery_round_trips(api, tmp_path):
    path = tmp_path / "m.pyfds"
    api.project.title = "saved"
    api.save(str(path))
    api.load(str(path))
    assert api.hygiene.recovery_available(str(path)) is None
    api.project.title = "unsaved work"
    recovery.write_autosave(api.project, path)
    assert Serializer().load(str(path)).title == "saved"
    os.utime(recovery.autosave_path(path), (time.time() + 5, time.time() + 5))
    info = api.hygiene.recovery_available(str(path))
    assert info and info["project_exists"]
    api.hygiene.recover(str(path))
    assert api.project.title == "unsaved work"
    api.save(str(path))                               # saving to the real file works (no protection) ...
    assert Serializer().load(str(path)).title == "unsaved work"
    assert api.hygiene.discard_recovery(str(path)) in (True, False)


def test_session_autosave_uses_side_file_and_save_removes_it(tmp_path):
    from pyfds.api.session import Session
    api = FdsApi()
    s = Session(api.project, str(tmp_path / "s.pyfds"))
    s.save()
    s.mark_dirty()
    recovery.write_autosave(api.project, s.filepath)
    assert recovery.autosave_path(s.filepath).is_file()
    s.save()
    assert not recovery.autosave_path(s.filepath).exists()


def test_backup_failure_never_blocks_open(tmp_path, monkeypatch):
    api = FdsApi()
    path = tmp_path / "m.pyfds"
    api.save(str(path))
    monkeypatch.setattr(recovery.shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    assert FdsApi().load(str(path)) is None


# -- remove all objects ----------------------------------------------------------------------
def test_remove_all_objects_is_one_undo_step_and_keeps_settings(api):
    api.meshes.add_mesh([10, 10, 10], [0, 1, 0, 1, 0, 1])
    api.project.add_entity(Surface(name="S"))
    api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1])
    api.obstructions.add_obstruction([2, 3, 0, 1, 0, 1])
    api.vents.add_vent([0, 1, 0, 0, 0, 1])
    api.devices.add_thermocouple([0.5, 0.5, 0.5], "T")
    assert api.hygiene.remove_all_objects() == {"obstructions": 2, "vents": 1, "devices": 1}
    assert len(api.project.meshes) == 1 and len(api.project.surfaces) == 1
    api.history.undo()
    assert len(api.project.obstructions) == 2 and len(api.project.vents) == 1 and len(api.project.devices) == 1
    assert api.hygiene.remove_all_objects(["meshes"]) == {"meshes": 1}
    with pytest.raises(KeyError):
        api.hygiene.remove_all_objects(["nope"])


# -- bulk rename -----------------------------------------------------------------------------
def test_bulk_rename_numbers_in_order_and_undoes_in_one_step(api):
    objs = [api.obstructions.add_obstruction([i, i + 1, 0, 1, 0, 1], name=f"o{i}") for i in range(3)]
    done = api.find.bulk_rename(objs, "Wall_{n:02d}", start=5, step=5)
    assert done == [("o0", "Wall_05"), ("o1", "Wall_10"), ("o2", "Wall_15")]
    api.history.undo()
    assert [o.name for o in objs] == ["o0", "o1", "o2"]


def test_bulk_rename_validation_and_references(api):
    a = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="a")
    b = api.obstructions.add_obstruction([2, 3, 0, 1, 0, 1], name="b")
    api.obstructions.add_obstruction([4, 5, 0, 1, 0, 1], name="Taken")
    with pytest.raises(ValueError, match="needs"):
        api.find.bulk_rename([a, b], "same")
    with pytest.raises(ValueError, match="clash"):
        api.find.bulk_rename([a], "Taken")
    with pytest.raises(ValueError, match="bad template"):
        api.find.bulk_rename([a], "{oops}")
    assert [a.name, b.name] == ["a", "b"]                         # nothing changed
    assert api.find.bulk_rename([a, b], "{name}_x") == [("a", "a_x"), ("b", "b_x")]
    api.project.add_entity(Surface(name="PAINT"))
    paint = api.project.surfaces[-1]
    o = api.obstructions.add_obstruction([6, 7, 0, 1, 0, 1], "PAINT")
    with pytest.raises(ValueError, match="referenced"):
        api.find.bulk_rename([paint], "ENAMEL")
    api.find.bulk_rename([paint], "ENAMEL", update_references=True)
    assert o.surface_id == "ENAMEL"


# -- preferences -----------------------------------------------------------------------------
def test_preferences_validation_and_undo_depth(api, restore_prefs):
    groups = api.preferences.all()
    assert "General" in groups and groups["General"]["undo_depth"]["value"] >= 10
    api.preferences.set("undo_depth", 25)
    assert api.history.depth == 25 and api.preferences.get("undo_depth") == 25
    api.preferences.set("recent_files_max", 0)
    for bad in (("undo_depth", 5), ("undo_depth", 25.5), ("undo_depth", True), ("create_backup_on_open", "yes"),
                ("auto_save_interval", 1), ("fds_binary", "  ")):
        with pytest.raises(ValueError):
            api.preferences.set(*bad)
    with pytest.raises(KeyError):
        api.preferences.set("bogus", 1)


# -- examples --------------------------------------------------------------------------------
@pytest.mark.parametrize("name", list(_EXAMPLES))
def test_every_example_builds_validates_and_writes(api, name):
    info = api.examples.load(name)
    assert info["name"] == name and api.project.chid == name
    report = api.validation.validate()
    assert not [i for i in getattr(report, "issues", []) if str(getattr(i.severity, "name", i.severity)).upper().startswith("ERR")]
    text = FdsWriter().to_string(api.project)
    assert "&MESH" in text and "&TAIL" in text
    assert not api.history.can_undo()


def test_unknown_example(api):
    with pytest.raises(KeyError):
        api.examples.load("nope")
    assert len(api.examples.list()) == len(_EXAMPLES) >= 5


# -- new-model defaults ------------------------------------------------------------------------
def test_model_defaults_are_a_catalogue_not_records(api):
    d = api.hygiene.model_defaults()
    assert len(d["reserved_surfaces"]) == 7 and len(d["species"]) == 9 and d["particle_classes"] == ["Tracer", "Water"]
    assert not api.project.species and not api.project.particles           # nothing written to the model
    assert api.hygiene.ensure_default_view() == "Default"
    assert api.hygiene.ensure_default_view() == "Default" and len(api.views.all()) == 1


def test_tools_registered():
    from pyfds.agent.registry import TOOL_REGISTRY
    names = {t.name for t in TOOL_REGISTRY}
    assert {"bulk_rename", "set_write_protection", "remove_all_objects", "recover_project", "load_example",
            "set_preference"} <= names
