"""Viewer preferences saved once per user (PyroSim's Results.props) and used by every new visualization."""
from __future__ import annotations

import pytest

from pyfds.api.facade import FdsApi
from pyfds.core import config
from pyfds.results.viz import user_prefs


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_CONFIG_DIR", tmp_path)
    return tmp_path


def test_new_visualization_starts_from_saved_defaults(user_dir):
    v = FdsApi().viewer
    v.set_fds_preferences(time_offset=2.5)
    v.set_smoke3d(preset="smoke_default")
    assert (user_dir / "results_prefs.json").exists() is False
    v.save_user_defaults()
    assert (user_dir / "results_prefs.json").exists()
    fresh = FdsApi().viewer
    fresh.new()
    assert fresh.viz.fds.time_offset == 2.5
    assert fresh.viz.smoke3d == v.viz.smoke3d


def test_without_a_file_nothing_changes(user_dir):
    v = FdsApi().viewer
    v.new()
    assert v.viz.fds.time_offset == 0.0
    assert v.load_user_defaults() is False


def test_apply_and_forget(user_dir):
    v = FdsApi().viewer
    v.set_fds_preferences(time_offset=4.0)
    v.save_user_defaults()
    v.set_fds_preferences(time_offset=0.0)
    assert v.load_user_defaults() is True and v.viz.fds.time_offset == 4.0
    assert v.clear_user_defaults() is True and v.clear_user_defaults() is False
    assert v.load_user_defaults() is False


def test_damaged_file_is_ignored(user_dir):
    (user_dir / "results_prefs.json").write_text("{not json", encoding="utf-8")
    v = FdsApi().viewer
    v.new()
    assert v.viz.fds.time_offset == 0.0
    (user_dir / "results_prefs.json").write_text('{"format": "other"}', encoding="utf-8")
    assert user_prefs.apply_user_defaults(v.viz) is False


def test_case_settings_are_not_saved_as_defaults(user_dir):
    v = FdsApi().viewer
    v.viz.geometry_set = "fds_actual"
    v.save_user_defaults()
    import json
    data = json.loads((user_dir / "results_prefs.json").read_text(encoding="utf-8"))
    assert "results" not in data and "views" not in data and "camera" not in data and "active" not in data
