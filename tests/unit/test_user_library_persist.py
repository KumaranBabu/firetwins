"""The user library persists at a default location outside the user profile (PYFDS_USER_DIR overrides it)."""
import os

from pyfds.api import FdsApi


def test_default_path_follows_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PYFDS_USER_DIR", str(tmp_path))
    assert FdsApi().library.default_path() == os.path.join(str(tmp_path), "user_library.json")


def test_library_survives_a_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("PYFDS_USER_DIR", str(tmp_path / "ud"))
    a = FdsApi()
    assert a.library.use_default_path() is not None
    cat = a.library.categories()[0]["key"]
    src = a.library.names(cat, "builtin")[0]
    a.library.add_to_model(cat, src, "Mine")
    a.library.add_to_library(cat, "Mine")
    assert os.path.exists(a.library.path)
    b = FdsApi()
    b.library.use_default_path()
    assert "Mine" in b.library.names(cat, "user")


def test_unwritable_location_stays_in_memory(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("PYFDS_USER_DIR", str(blocker / "sub"))
    a = FdsApi()
    assert a.library.use_default_path() is None and a.library.path is None
