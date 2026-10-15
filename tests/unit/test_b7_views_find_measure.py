"""B7: saved views, section box, selection/view history, find/replace, measuring."""
import pytest

from pyfds.api import FdsApi
from pyfds.core.viewport_types import CameraPreset
from pyfds.domain import measure as M
from pyfds.domain.model import Surface
from pyfds.domain.views import SectionBox
from pyfds.io.serializer import Serializer


def test_section_box_geometry():
    b = SectionBox(x_min=0, x_max=5, z_max=3)
    assert b.contains((1, 100, -50)) and not b.contains((6, 0, 0)) and not b.contains((1, 0, 4))
    assert b.intersects([4, 9, 0, 1, 0, 1]) and not b.intersects([6, 9, 0, 1, 0, 1])
    assert b.clip_planes() == [("x", 0, "above"), ("x", 5, "below"), ("z", 3, "below")]
    b.enabled = False
    assert b.contains((99, 99, 99)) and b.clip_planes() == []
    with pytest.raises(ValueError):
        SectionBox(x_min=2, x_max=1).validate()


def test_views_save_apply_persist(tmp_path):
    api = FdsApi()
    api.viewport.apply_preset(CameraPreset.TOP, 20)
    api.views.set_section_box(x_min=0, x_max=4)
    api.view.set_type_visible("vents", False)
    api.views.save_viewpoint("plan", "top view")
    api.views.reset_section_box()
    api.view.show_all()
    api.viewport.apply_preset(CameraPreset.FRONT, 5)
    api.views.reset_to("plan")
    assert api.views.section_box().x_max == 4 and api.view.hidden_types() == ["vents"]
    assert api.viewport.state.camera.position[2] == pytest.approx(20)
    path = tmp_path / "v.pyfds"
    Serializer().save(api.project, str(path))
    loaded = Serializer().load(str(path)).editor
    assert loaded.active_view == "plan" and loaded.views["plan"].description == "top view"
    assert loaded.section_box.x_max == 4


def test_view_management_errors():
    api = FdsApi()
    api.views.new_view("a")
    with pytest.raises(ValueError):
        api.views.new_view("a")
    api.views.duplicate("a", "b")
    api.views.rename("b", "c")
    assert {v.name for v in api.views.all()} == {"a", "c"}
    api.views.delete("a")
    with pytest.raises(KeyError):
        api.views.reset_to("zzz")
    with pytest.raises(ValueError):
        api.views.set_section_enabled(True)


def test_fit_section_box_and_clipped_out():
    api = FdsApi()
    near = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1])
    far = api.obstructions.add_obstruction([20, 21, 0, 1, 0, 1])
    box = api.views.fit_section_box([near], margin=0.5)
    assert (box.x_min, box.x_max) == (-0.5, 1.5)
    assert api.views.clipped_out() == [far]
    api.views.set_section_enabled(False)
    assert api.views.clipped_out() == []


def test_ui_history_separate_from_model_history():
    api = FdsApi()
    a = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1])
    b = api.obstructions.add_obstruction([2, 3, 0, 1, 0, 1])
    api.ui_history.clear()
    api.selection.select(a)
    api.selection.select(b)
    api.views.set_section_box(x_max=2)
    assert api.ui_history.labels() == ["selection", "selection", "set section box"]
    assert api.ui_history.undo() == "set section box" and api.views.section_box() is None
    assert api.ui_history.undo() == "selection"
    assert [e.uid for e in api.selection.selected] == [a.uid]
    assert api.ui_history.redo() == "selection"
    assert [e.uid for e in api.selection.selected] == [b.uid]
    assert len(api.project.obstructions) == 2          # model untouched by UI undo
    api.history.undo()                                  # "Undo Edit" removes b; UI stack is untouched
    assert len(api.project.obstructions) == 1 and api.ui_history.can_undo


def test_find_and_select():
    api = FdsApi()
    a = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="Desk_1", tags=["office"])
    api.obstructions.add_obstruction([2, 3, 0, 1, 0, 1], name="Wall_1")
    assert [m.entity for m in api.find.find("desk")] == [a]
    assert api.find.find("desk", case_sensitive=True) == []
    assert [m.field for m in api.find.find("office", fields=("tags",))] == ["tags"]
    assert len(api.find.find(r"_\d", regex=True)) == 2
    assert api.find.find("Desk", whole_word=True) == []
    api.find.find("Wall", select=True)
    assert [e.name for e in api.selection.selected] == ["Wall_1"]
    with pytest.raises(ValueError):
        api.find.find("")
    with pytest.raises(ValueError):
        api.find.find("x", fields=("color",))
    with pytest.raises(KeyError):
        api.find.find("x", kinds=["nope"])


def test_replace_names_one_undo_step_and_collisions():
    api = FdsApi()
    api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="Desk_1")
    api.obstructions.add_obstruction([2, 3, 0, 1, 0, 1], name="Desk_2")
    api.obstructions.add_obstruction([4, 5, 0, 1, 0, 1], name="Chair_2")
    preview = api.find.replace("Desk", "Table", dry_run=True)
    assert len(preview["changed"]) == 2 and api.project.obstructions[0].name == "Desk_1"
    r = api.find.replace("Desk", "Table")
    assert [n for _, _, n in r["changed"]] == ["Table_1", "Table_2"]
    api.history.undo()
    assert [o.name for o in api.project.obstructions] == ["Desk_1", "Desk_2", "Chair_2"]
    r = api.find.replace("Desk_1", "Chair_2")
    assert r["skipped"] and "already exists" in r["skipped"][0][1]
    r = api.find.replace("Desk_1", "  ")
    assert "empty" in r["skipped"][0][1]


def test_replace_referenced_name_needs_update_references():
    api = FdsApi()
    api.project.add_entity(Surface(name="PAINT"))
    o = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], surf_id="PAINT")
    r = api.find.replace("PAINT", "ENAMEL", kinds=["surfaces"])
    assert r["skipped"] and api.project.surfaces[-1].name == "PAINT"
    r = api.find.replace("PAINT", "ENAMEL", kinds=["surfaces"], update_references=True)
    assert r["changed"] and o.surface_id == "ENAMEL" and api.project.surfaces[-1].name == "ENAMEL"
    api.history.undo()
    assert o.surface_id == "PAINT" and api.project.surfaces[-1].name == "PAINT"


def test_replace_tags_and_description():
    api = FdsApi()
    e = api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="A", tags=["old", "keep"], description="old stuff")
    api.find.replace("old", "new", fields=("tags", "description"))
    assert e.tags == ["new", "keep"] and e.description == "new stuff"


def test_measure_functions():
    d = M.distance((0, 0, 0), (3, 4, 12))
    assert d["distance"] == pytest.approx(13) and d["horizontal"] == pytest.approx(5)
    assert M.angle((1, 0, 0), (0, 0, 0), (0, 1, 0)) == pytest.approx(90)
    assert M.path_length([(0, 0, 0), (3, 0, 0), (3, 4, 0)]) == pytest.approx(7)
    assert M.polygon_area([(0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)]) == pytest.approx(12)
    assert M.polygon_area([(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2)]) == pytest.approx(4)   # a vertical wall
    g = M.box_gap([0, 1, 0, 1, 0, 1], [4, 5, 0, 1, 0, 1])
    assert g["gap"] == pytest.approx(3) and g["gap_y"] == 0
    assert M.box_gap([0, 2, 0, 2, 0, 2], [1, 3, 1, 3, 1, 3])["gap"] == 0
    assert M.box_size([0, 2, 0, 3, 0, 4])["volume"] == 24
    with pytest.raises(ValueError):
        M.angle((0, 0, 0), (0, 0, 0), (1, 0, 0))
    with pytest.raises(ValueError):
        M.path_length([(0, 0, 0)])


def test_api_measure_between_objects_by_name():
    api = FdsApi()
    api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1], name="A")
    api.obstructions.add_obstruction([3, 4, 0, 1, 0, 1], name="B")
    assert api.measure.between("A", "B")["gap"] == pytest.approx(2)
    assert api.measure.size("B")["dx"] == 1
    with pytest.raises(KeyError):
        api.measure.between("A", "ZZZ")
    with pytest.raises(ValueError):
        api.measure.between(api.project.misc, api.project.obstructions[0])


def test_tools_registered():
    from pyfds.agent.registry import TOOL_REGISTRY
    names = {t.name for t in TOOL_REGISTRY}
    assert {"save_view", "set_section_box", "find_objects", "replace_text", "measure_distance",
            "undo_selection_view"} <= names
