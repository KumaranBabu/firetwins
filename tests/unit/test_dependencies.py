"""api.dependencies: who uses an object, and delete with a replacement (PyroSim 2025.1)."""
from __future__ import annotations

import pytest

from pyfds.api import FdsApi
from pyfds.domain.model import Surface


@pytest.fixture
def api():
    a = FdsApi()
    a.surfaces.add(Surface(name="PAINT_A"))
    a.surfaces.add(Surface(name="PAINT_B"))
    a.obstructions.add_obstruction(xb=[0, 1, 0, 1, 0, 1], name="o1", surf_id="PAINT_A")
    a.obstructions.add_obstruction(xb=[2, 3, 0, 1, 0, 1], name="o2", surf_id="PAINT_A")
    a.obstructions.add_obstruction(xb=[4, 5, 0, 1, 0, 1], name="o3", surf_id="PAINT_B")
    return a


def _surface(api, name):
    return next(s for s in api.surfaces.all() if s.name == name)


def test_dependents_lists_every_use(api):
    uses = api.dependencies.dependents(_surface(api, "PAINT_A"))
    assert sorted((o.name, f) for o, f in uses) == [("o1", "surface_id"), ("o2", "surface_id")]
    assert api.dependencies.dependents(_surface(api, "PAINT_B"))[0][0].name == "o3"


def test_delete_with_replacement_repoints_the_uses_in_one_undo_step(api):
    n = api.dependencies.delete(_surface(api, "PAINT_A"), replacement="PAINT_B")
    assert n == 2
    assert [s.name for s in api.surfaces.all()] == ["PAINT_B"]
    assert {o.name: o.surface_id for o in api.obstructions.all()} == {"o1": "PAINT_B", "o2": "PAINT_B", "o3": "PAINT_B"}
    api.history.undo()
    assert sorted(s.name for s in api.surfaces.all()) == ["PAINT_A", "PAINT_B"]
    assert {o.name: o.surface_id for o in api.obstructions.all()}["o1"] == "PAINT_A"


def test_delete_without_replacement_leaves_the_uses_alone(api):
    assert api.dependencies.delete(_surface(api, "PAINT_A")) == 0
    assert {o.name: o.surface_id for o in api.obstructions.all()}["o1"] == "PAINT_A"


def test_bad_replacement_is_refused_and_nothing_changes(api):
    with pytest.raises(ValueError):
        api.dependencies.delete(_surface(api, "PAINT_A"), replacement="NOPE")
    with pytest.raises(ValueError):
        api.dependencies.delete(_surface(api, "PAINT_A"), replacement="PAINT_A")
    assert len(api.surfaces.all()) == 2
