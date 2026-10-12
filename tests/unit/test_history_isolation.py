"""Undo/redo history is per document and configure_simulation is undoable."""
import pytest

from pyfds.api import FdsApi


def _mesh(api, name="m"):
    api.meshes.add_mesh(ijk=(10, 10, 10), xb=(0, 1, 0, 1, 0, 1), name=name)


def test_new_project_does_not_inherit_previous_history():
    api = FdsApi()
    api.new("a")
    _mesh(api)
    project_a = api.project
    api.new("b")
    assert not api.history.can_undo()
    api.history.undo()  # no-op, must not touch project "a"
    assert len(project_a.meshes) == 1


def test_switching_documents_keeps_each_history(tmp_path):
    api = FdsApi()
    api.session.new_project("a")
    _mesh(api)
    api.session.new_project("b")
    assert not api.history.can_undo()
    _mesh(api, "b1")
    _mesh(api, "b2")
    api.session.switch_project("a")
    assert api.history.history() == ["add Mesh 'm'"]
    api.history.undo()
    assert len(api.project.meshes) == 0
    api.session.switch_project("b")
    assert len(api.project.meshes) == 2
    assert len(api.history.history()) == 2


def test_closed_documents_history_is_pruned():
    api = FdsApi()
    api.session.new_project("a")
    api.session.new_project("b")
    api.session.close_project("a")
    api.new("c")
    assert len(api.history._pipes) <= 2


def test_configure_simulation_is_one_undo_step():
    api = FdsApi()
    api.new("a")
    before = (api.project.params.t_end, api.project.params.t_begin)
    api.config.configure_simulation(t_end=123.0, t_begin=5.0)
    assert (api.project.params.t_end, api.project.params.t_begin) == (123.0, 5.0)
    assert len(api.history.history()) == 1
    api.history.undo()
    assert (api.project.params.t_end, api.project.params.t_begin) == before
    api.history.redo()
    assert api.project.params.t_end == 123.0


def test_configure_simulation_noop_records_nothing():
    api = FdsApi()
    api.new("a")
    api.config.configure_simulation()
    assert not api.history.can_undo()
