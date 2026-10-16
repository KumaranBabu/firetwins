"""Every example model must pass the run gate (a run is refused when the model has validation errors), and drawing
several unnamed objects must not give them all the same name."""
import pytest

from pyfds.api import FdsApi

NAMES = [e["name"] for e in FdsApi().examples.list()]


@pytest.mark.parametrize("name", NAMES)
def test_example_passes_the_run_gate(name):
    api = FdsApi()
    api.examples.load(name)
    api.validation.gate()                                   # raises ValidationGateError when the example cannot run


def test_unnamed_objects_get_distinct_names_and_a_given_name_is_kept():
    api = FdsApi()
    v = [api.vents.add_vent([0, 1, 0, 0, 0, 1]) for _ in range(3)]
    assert [x.name for x in v] == ["Vent", "Vent2", "Vent3"]
    o = [api.obstructions.add_obstruction([0, 1, 0, 1, 0, 1]) for _ in range(2)]
    assert [x.name for x in o] == ["Obstruction", "Obstruction2"]
    h = [api.holes.add_hole([0, 1, 0, 1, 0, 1]) for _ in range(2)]
    assert [x.name for x in h] == ["Hole", "Hole2"]
    assert api.vents.add_vent([0, 1, 0, 0, 0, 1], name="DOOR").name == "DOOR"
    api.history.undo()
    assert api.vents.add_vent([0, 1, 0, 0, 0, 1]).name == "Vent4"          # the undone DOOR does not matter; Vent..Vent3 remain
