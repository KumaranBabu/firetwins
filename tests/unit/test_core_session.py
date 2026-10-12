"""Unit tests — pyfds.api.session (Session, SessionManager)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from pyfds.api.session import Session, SessionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(chid="test_case", title="Test"):
    proj = MagicMock()
    proj.chid = chid
    proj.title = title
    return proj


# ---------------------------------------------------------------------------
# Session — creation and identity
# ---------------------------------------------------------------------------

class TestSessionCreation:
    def test_session_has_unique_id(self):
        p = _make_project()
        s1 = Session(p)
        s2 = Session(p)
        assert s1.session_id != s2.session_id

    def test_initial_not_dirty(self):
        s = Session(_make_project())
        assert s.is_dirty is False

    def test_filepath_none_when_not_provided(self):
        s = Session(_make_project())
        assert s.filepath is None

    def test_filepath_set_from_string(self):
        from pathlib import Path
        s = Session(_make_project(), filepath="C:/cases/test.fds")
        assert s.filepath == Path("C:/cases/test.fds")

    def test_project_stored(self):
        p = _make_project(chid="my_case")
        s = Session(p)
        assert s.project is p


# ---------------------------------------------------------------------------
# Session — dirty tracking
# ---------------------------------------------------------------------------

class TestSessionDirtyTracking:
    def test_mark_dirty(self):
        s = Session(_make_project())
        s.mark_dirty()
        assert s.is_dirty is True

    def test_mark_clean_clears_dirty(self):
        s = Session(_make_project())
        s.mark_dirty()
        s.mark_clean()
        assert s.is_dirty is False

    def test_mark_clean_sets_last_saved(self):
        s = Session(_make_project())
        s.mark_clean()
        assert s._last_saved_at is not None


# ---------------------------------------------------------------------------
# Session — to_dict
# ---------------------------------------------------------------------------

class TestSessionToDict:
    def test_to_dict_has_expected_keys(self):
        s = Session(_make_project(chid="hotel_fire"))
        d = s.to_dict()
        assert "session_id" in d
        assert "filepath" in d
        assert "is_dirty" in d
        assert "chid" in d

    def test_to_dict_chid_from_project(self):
        s = Session(_make_project(chid="hotel_fire"))
        assert s.to_dict()["chid"] == "hotel_fire"

    def test_to_dict_filepath_none_when_unset(self):
        s = Session(_make_project())
        assert s.to_dict()["filepath"] is None

    def test_repr_contains_unsaved(self):
        s = Session(_make_project())
        assert "<unsaved>" in repr(s)

    def test_repr_contains_dirty_when_dirty(self):
        s = Session(_make_project())
        s.mark_dirty()
        assert "[dirty]" in repr(s)


# ---------------------------------------------------------------------------
# Session — save / load (mocked I/O)
# ---------------------------------------------------------------------------

class TestSessionSave:
    def test_save_raises_without_filepath(self):
        s = Session(_make_project())
        with pytest.raises(ValueError, match="filepath"):
            s.save()

    def test_save_marks_clean(self, tmp_path):
        mock_serializer = MagicMock()
        mock_serializer.return_value.save = MagicMock()
        with patch("pyfds.io.serializer.Serializer", mock_serializer):
            s = Session(_make_project())
            s.mark_dirty()
            s.save(filepath=str(tmp_path / "case.pyfds"))
        assert s.is_dirty is False

    def test_save_updates_filepath(self, tmp_path):
        target = tmp_path / "case.pyfds"
        mock_serializer = MagicMock()
        mock_serializer.return_value.save = MagicMock()
        with patch("pyfds.io.serializer.Serializer", mock_serializer):
            s = Session(_make_project())
            s.save(filepath=str(target))
        assert s.filepath is not None


class TestSessionLoad:
    def test_load_pyfds_uses_serializer(self):
        mock_serializer = MagicMock()
        mock_serializer.return_value.load.return_value = _make_project(chid="loaded")
        with patch("pyfds.io.serializer.Serializer", mock_serializer):
            s = Session(_make_project())
            s.load("case.pyfds")
        mock_serializer.return_value.load.assert_called_once()

    def test_load_fds_uses_parser(self):
        mock_parser = MagicMock()
        mock_parser.return_value.parse.return_value = _make_project(chid="parsed")
        with patch("pyfds.io.fds_parser.FdsParser", mock_parser):
            s = Session(_make_project())
            s.load("case.fds")
        mock_parser.return_value.parse.assert_called_once()

    def test_load_marks_clean(self):
        mock_serializer = MagicMock()
        mock_serializer.return_value.load.return_value = _make_project()
        with patch("pyfds.io.serializer.Serializer", mock_serializer):
            s = Session(_make_project())
            s.mark_dirty()
            s.load("case.pyfds")
        assert s.is_dirty is False


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class TestSessionManager:
    def test_new_session_registered(self):
        mgr = SessionManager()
        s = mgr.new_session(_make_project())
        assert mgr.get(s.session_id) is s

    def test_new_session_becomes_active(self):
        mgr = SessionManager()
        s = mgr.new_session(_make_project())
        assert mgr.active is s

    def test_count_increments(self):
        mgr = SessionManager()
        mgr.new_session(_make_project())
        mgr.new_session(_make_project())
        assert mgr.count == 2

    def test_all_sessions_returns_list(self):
        mgr = SessionManager()
        mgr.new_session(_make_project())
        mgr.new_session(_make_project())
        assert len(mgr.all_sessions) == 2

    def test_close_clean_session(self):
        mgr = SessionManager()
        s = mgr.new_session(_make_project())
        mgr.close(s.session_id)
        assert mgr.count == 0

    def test_close_dirty_raises_without_force(self):
        mgr = SessionManager()
        s = mgr.new_session(_make_project())
        s.mark_dirty()
        with pytest.raises(RuntimeError, match="unsaved"):
            mgr.close(s.session_id, force=False)

    def test_close_dirty_with_force(self):
        mgr = SessionManager()
        s = mgr.new_session(_make_project())
        s.mark_dirty()
        mgr.close(s.session_id, force=True)
        assert mgr.count == 0

    def test_close_unknown_id_no_error(self):
        mgr = SessionManager()
        mgr.close("nonexistent-id")

    def test_close_all(self):
        mgr = SessionManager()
        mgr.new_session(_make_project())
        mgr.new_session(_make_project())
        mgr.close_all()
        assert mgr.count == 0

    def test_set_active_switches_session(self):
        mgr = SessionManager()
        s1 = mgr.new_session(_make_project())
        s2 = mgr.new_session(_make_project())
        mgr.set_active(s1.session_id)
        assert mgr.active is s1

    def test_set_active_unknown_raises(self):
        mgr = SessionManager()
        with pytest.raises(KeyError):
            mgr.set_active("bad-id")

    def test_active_none_when_empty(self):
        mgr = SessionManager()
        assert mgr.active is None

    def test_status_returns_list_of_dicts(self):
        mgr = SessionManager()
        mgr.new_session(_make_project())
        status = mgr.status()
        assert isinstance(status, list)
        assert "session_id" in status[0]

    def test_repr_contains_count(self):
        mgr = SessionManager()
        mgr.new_session(_make_project())
        assert "sessions=1" in repr(mgr)
