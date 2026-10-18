"""Preferences are kept between sessions (F1): the dialog saves user_data/config.json, a new config object reads it back."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import pyfds.core.config as cfg_mod  # noqa: E402
from tests.mw_proxy import main_window_mod as mw  # noqa: E402
from tests.unit.test_main_window_phase2_part1 import _fake_dialog_returning, _make_window  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QApplication.instance() or QApplication([])


def test_preferences_dialog_saves_and_a_new_config_reads_them_back(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning(
        {"fds_binary": "/opt/fds6/fds", "auto_save": True, "undo_depth": 50}))
    window._on_preferences()
    saved = json.loads(cfg_mod._CONFIG_FILE.read_text(encoding="utf-8"))
    assert saved["fds_binary"] == "/opt/fds6/fds" and saved["auto_save"] is True and saved["undo_depth"] == 50
    fresh = cfg_mod.FdsConfig()
    assert fresh.get("fds_binary") == "/opt/fds6/fds" and fresh.get("auto_save") is True
    window.close()


def test_undo_depth_from_the_dialog_applies_now(monkeypatch):
    window = _make_window()
    monkeypatch.setattr(mw, "SchemaFormDialog", _fake_dialog_returning({"undo_depth": 25}))
    window._on_preferences()
    assert window.api.history.depth == 25
    window.close()


def test_the_config_file_is_never_under_the_user_profile():
    from pathlib import Path
    assert Path.home() not in cfg_mod._user_dir().parents
