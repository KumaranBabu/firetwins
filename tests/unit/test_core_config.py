"""Unit tests — pyfds.core.config (FdsConfig, ConfigProfile, get_config)."""
from __future__ import annotations

import os
import json
import pytest
from unittest.mock import patch
from pathlib import Path

from pyfds.core.config import (
    FdsConfig, ConfigProfile, get_config, reset_config,
    _DEFAULTS,
)


# ---------------------------------------------------------------------------
# ConfigProfile
# ---------------------------------------------------------------------------

class TestConfigProfile:
    def test_default_overrides_empty(self):
        p = ConfigProfile("test")
        assert p.overrides == {}

    def test_get_returns_override(self):
        p = ConfigProfile("test", overrides={"fds_binary": "/bin/fds"})
        assert p.get("fds_binary") == "/bin/fds"

    def test_get_returns_default_when_missing(self):
        p = ConfigProfile("test")
        assert p.get("missing_key", "fallback") == "fallback"

    def test_set_adds_override(self):
        p = ConfigProfile("test")
        p.set("fds_binary", "/opt/fds")
        assert p.overrides["fds_binary"] == "/opt/fds"

    def test_to_dict_roundtrip(self):
        p = ConfigProfile("dev", overrides={"log_level": "DEBUG"})
        d = p.to_dict()
        restored = ConfigProfile.from_dict(d)
        assert restored.name == "dev"
        assert restored.overrides["log_level"] == "DEBUG"

    def test_to_dict_deep_copy(self):
        p = ConfigProfile("x", overrides={"plugin_dirs": ["/a"]})
        d = p.to_dict()
        d["overrides"]["plugin_dirs"].append("/b")
        assert p.overrides["plugin_dirs"] == ["/a"]

    def test_from_dict_missing_overrides(self):
        p = ConfigProfile.from_dict({"name": "empty"})
        assert p.overrides == {}


# ---------------------------------------------------------------------------
# FdsConfig — basic get/set
# ---------------------------------------------------------------------------

class TestFdsConfigBasic:
    def setup_method(self):
        reset_config()

    def test_defaults_populated(self):
        cfg = FdsConfig()
        assert cfg.fds_binary == _DEFAULTS["fds_binary"]

    def test_set_creates_runtime_override(self):
        cfg = FdsConfig()
        cfg.set("fds_binary", "/custom/fds")
        assert cfg.fds_binary == "/custom/fds"

    def test_set_many(self):
        cfg = FdsConfig()
        cfg.set_many({"fds_binary": "/a", "smv_binary": "/b"})
        assert cfg.fds_binary == "/a"
        assert cfg.smv_binary == "/b"

    def test_get_default_for_unknown_key(self):
        cfg = FdsConfig()
        assert cfg.get("no_such_key", 42) == 42

    def test_runtime_overrides_profile(self):
        cfg = FdsConfig()
        cfg.set_profile("hpc")
        cfg.save_profile("hpc", {"fds_binary": "/hpc/fds"})
        cfg.set("fds_binary", "/runtime/fds")
        assert cfg.fds_binary == "/runtime/fds"


# ---------------------------------------------------------------------------
# FdsConfig — convenience properties
# ---------------------------------------------------------------------------

class TestFdsConfigProperties:
    def test_temp_directory_is_path(self):
        cfg = FdsConfig()
        assert isinstance(cfg.temp_directory, Path)

    def test_output_directory_is_path(self):
        cfg = FdsConfig()
        assert isinstance(cfg.output_directory, Path)

    def test_default_mpi_processes(self):
        cfg = FdsConfig()
        assert isinstance(cfg.default_mpi_processes, int)
        assert cfg.default_mpi_processes >= 1

    def test_auto_validate_default_true(self):
        cfg = FdsConfig()
        assert cfg.auto_validate is True

    def test_max_job_workers_positive(self):
        cfg = FdsConfig()
        assert cfg.max_job_workers > 0

    def test_job_timeout_default_none(self):
        cfg = FdsConfig()
        assert cfg.job_timeout is None

    def test_plugin_dirs_default_empty_list(self):
        cfg = FdsConfig()
        assert cfg.plugin_dirs == []

    def test_set_job_timeout_float(self):
        cfg = FdsConfig()
        cfg.set("job_timeout", 3600)
        assert cfg.job_timeout == 3600.0

    def test_to_dict_contains_keys(self):
        cfg = FdsConfig()
        d = cfg.to_dict()
        assert "fds_binary" in d
        assert "active_profile" in d


# ---------------------------------------------------------------------------
# FdsConfig — profiles
# ---------------------------------------------------------------------------

class TestFdsConfigProfiles:
    def test_default_profile_exists(self):
        cfg = FdsConfig()
        assert "default" in cfg.profile_names

    def test_set_profile_creates_new(self):
        cfg = FdsConfig()
        cfg.set_profile("cluster")
        assert "cluster" in cfg.profile_names

    def test_active_profile_affects_get(self):
        cfg = FdsConfig()
        cfg.set_profile("cluster")
        cfg.save_profile("cluster", {"fds_binary": "/cluster/fds"})
        assert cfg.fds_binary == "/cluster/fds"

    def test_save_profile_with_explicit_overrides(self):
        cfg = FdsConfig()
        cfg.save_profile("p1", {"max_job_workers": 8})
        p = cfg.get_profile("p1")
        assert p is not None
        assert p.overrides["max_job_workers"] == 8

    def test_save_profile_from_runtime(self):
        cfg = FdsConfig()
        cfg.set("max_job_workers", 16)
        cfg.save_profile("saved")
        p = cfg.get_profile("saved")
        assert p.overrides["max_job_workers"] == 16

    def test_get_nonexistent_profile_returns_none(self):
        cfg = FdsConfig()
        assert cfg.get_profile("nonexistent") is None


# ---------------------------------------------------------------------------
# FdsConfig — persistence (mocked file I/O)
# ---------------------------------------------------------------------------

class TestFdsConfigPersistence:
    def test_save_and_reload(self, tmp_path):
        with patch("pyfds.core.config._CONFIG_DIR", tmp_path), \
             patch("pyfds.core.config._CONFIG_FILE", tmp_path / "config.json"):
            cfg = FdsConfig()
            cfg.set("max_job_workers", 99)
            cfg.save()
            assert (tmp_path / "config.json").exists()
            data = json.loads((tmp_path / "config.json").read_text())
            assert data["max_job_workers"] == 99

    def test_reload_loads_from_file(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"max_job_workers": 77}))
        with patch("pyfds.core.config._CONFIG_DIR", tmp_path), \
             patch("pyfds.core.config._CONFIG_FILE", config_file):
            cfg = FdsConfig()
        assert cfg.get("max_job_workers") == 77

    def test_corrupt_file_does_not_crash(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("NOT VALID JSON {{{")
        with patch("pyfds.core.config._CONFIG_DIR", tmp_path), \
             patch("pyfds.core.config._CONFIG_FILE", config_file):
            cfg = FdsConfig()
        assert cfg.fds_binary is not None


# ---------------------------------------------------------------------------
# FdsConfig — environment variable mapping
# ---------------------------------------------------------------------------

class TestFdsConfigEnvVars:
    def test_env_var_overrides_default(self):
        with patch.dict(os.environ, {"PYFDS_FDS_BIN": "/env/fds"}):
            cfg = FdsConfig()
        assert cfg.fds_binary == "/env/fds"

    def test_mpi_env_var_coerced_to_int(self):
        with patch.dict(os.environ, {"PYFDS_MPI": "4"}):
            cfg = FdsConfig()
        assert cfg.default_mpi_processes == 4


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

class TestGetConfig:
    def test_get_config_returns_instance(self):
        reset_config()
        cfg = get_config()
        assert isinstance(cfg, FdsConfig)

    def test_get_config_same_object(self):
        reset_config()
        assert get_config() is get_config()

    def test_reset_config_creates_new_instance(self):
        a = get_config()
        reset_config()
        b = get_config()
        assert a is not b

    def test_repr_contains_profile(self):
        cfg = FdsConfig()
        assert "default" in repr(cfg)
