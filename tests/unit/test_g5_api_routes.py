"""G5: what the GUI and CLI used to import directly now lives on the api (transform, add_entity,
HVAC node moves, result readers, batch config)."""
import json

import pytest

from pyfds.api import FdsApi
from pyfds.domain.model import HvacNode


@pytest.fixture
def api():
    return FdsApi()


def _box(api, x, name):
    return api.obstructions.add_obstruction([x, x + 1, 0, 1, 0, 1], name=name)


# -- transform ----------------------------------------------------------------------------------
def test_move_is_one_undo_step_and_skips_what_has_no_position(api):
    a, b = _box(api, 0, "a"), _box(api, 3, "b")
    s = api.surfaces.add_typed("basic", "S")
    r = api.transform.move([a, b, s], dx=2, dz=1)
    assert r == {"transformed": 2, "skipped": 1}
    assert (a.x_min, a.z_min, b.x_min) == (2, 1, 5)
    api.history.undo()
    assert (a.x_min, a.z_min, b.x_min) == (0, 0, 3)


def test_rotate_pivots_about_the_shared_centre(api):
    a, b = _box(api, 0, "a"), _box(api, 3, "b")      # centre of both: x = 2, y = 0.5
    api.transform.rotate([a, b], 180)
    assert (a.x_min, a.x_max) == pytest.approx((3, 4)) and (b.x_min, b.x_max) == pytest.approx((0, 1))


def test_rotate_non_right_angle_skips_boxes_but_moves_points(api):
    a = _box(api, 0, "a")
    d = api.devices.add_thermocouple([1.0, 0.0, 1.0], "T")
    r = api.transform.rotate([a, d], 17.5)
    assert r == {"transformed": 1, "skipped": 1}
    with pytest.raises(ValueError, match="nothing"):
        api.transform.rotate([a], 17.5)


def test_scale_and_mirror(api):
    a, b = _box(api, 0, "a"), _box(api, 3, "b")      # x spans 0..4, centre 2
    api.transform.scale([a, b], 2.0)
    assert (a.x_min, b.x_max) == pytest.approx((-2, 6))
    api.history.undo()
    api.transform.mirror([a, b], "x")
    assert (a.x_min, a.x_max) == pytest.approx((3, 4)) and (b.x_min, b.x_max) == pytest.approx((0, 1))
    with pytest.raises(ValueError):
        api.transform.scale([a], 0)
    with pytest.raises(ValueError):
        api.transform.mirror([a], "W")


def test_groups_move_as_one_unit(api):
    a, b, c = _box(api, 0, "a"), _box(api, 3, "b"), _box(api, 9, "c")
    api.groups.create("pair")
    api.groups.assign(a, "pair")
    api.groups.assign(b, "pair")
    assert {e.name for e in api.transform.expand_groups([a])} == {"a", "b"}
    api.transform.move([a], dx=1)
    assert (a.x_min, b.x_min, c.x_min) == (1, 4, 9)
    api.transform.move([a], dx=1, expand_groups=False)
    assert (a.x_min, b.x_min) == (2, 4)


# -- add_entity / HVAC --------------------------------------------------------------------------
def test_add_entity_is_undoable(api):
    from pyfds.domain.model import Obstruction
    o = Obstruction(name="new", x_min=0, x_max=1, y_min=0, y_max=1, z_min=0, z_max=1)
    assert api.add_entity(o) is o and o in api.project.obstructions
    api.history.undo()
    assert o not in api.project.obstructions


def test_hvac_move_nodes_batches_into_one_step(api):
    n1 = HvacNode(name="N1", x=0, y=0, z=0)
    n2 = HvacNode(name="N2", x=1, y=1, z=0)
    api.project.add_entity(n1)
    api.project.add_entity(n2)
    assert api.hvac.move_nodes([(n1, 2, 0), (n2, 0, 3), (n1, 0, 0)], label="layout") == 2
    assert (n1.x, n2.y) == (2, 4)
    api.history.undo()
    assert (n1.x, n2.y) == (0, 1)
    assert api.hvac.move_nodes([(n1, 0, 0)]) == 0


# -- results / batch / misc ----------------------------------------------------------------------
def test_device_figure_needs_an_index(api):
    with pytest.raises(RuntimeError, match="index"):
        api.results.device_figure("TC1")

    class Idx:
        def find_device_file(self, name):
            return None
    with pytest.raises(KeyError):
        api.results.device_figure("TC1", index=Idx())


def test_readers_and_summary_fail_cleanly_on_missing_files(api, tmp_path):
    with pytest.raises(Exception):
        api.results.smv_metadata(str(tmp_path / "nope.smv"))
    with pytest.raises(Exception):
        api.results.plot3d(str(tmp_path / "nope.q"))


def test_batch_load_config_reports_a_readable_error(api, tmp_path):
    bad = tmp_path / "b.json"
    bad.write_text(json.dumps({"name": "x"}))
    with pytest.raises(ValueError):
        api.batch.load_config(str(bad))


def test_collection_names(api):
    names = api.find.collection_names()
    assert "obstructions" in names and "surfaces" in names and names == sorted(names)


def test_fds_text_replaces_direct_writer_use(api):
    _box(api, 0, "a")
    assert "&OBST" in api.fds_text()


def test_cli_info_and_report_go_through_the_api(tmp_path, capsys):
    from pyfds.cli.main import main
    api = FdsApi()
    api.save(str(tmp_path / "m.pyfds"))
    assert main(["info", str(tmp_path / "m.pyfds")]) == 0
    assert main(["info", str(tmp_path / "m.xyz")]) == 1
