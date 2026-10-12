"""
Tests for:
  - SMV-enhanced ResultIndex (build_from_smv, _ingest_smv, smv_devices, etc.)
  - BatchStudyConfig validation and round-trip
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from pyfds.results.indexer import ResultIndex, SliceIndex, BoundaryIndex
from pyfds.execution.batch_config import BatchStudyConfig, BatchConfigError, AxisConfig


# ─────────────────────────────────────────────────────────────────────────────
# SMV fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

SMV_CONTENT = textwrap.dedent("""\
CHID room_fire
TITLE Room fire test
VERSION FDS 6.8.0

GRID
 20 20 10
PDIM
 0.0 4.0 0.0 4.0 0.0 2.0

SLCF
 room_fire_01.sf
 TEMPERATURE TEMPERATURE degC
 0 20 0 20 0 0

BNDF
 room_fire_01.bf
 HEAT_FLUX HEAT_FLUX kW/m2

DEVICE
 TC_01
 2.0 2.0 1.5 0.0 0.0 0.0 TEMPERATURE degC

DEVICE
 TC_02
 1.0 1.0 1.0 0.0 0.0 0.0 TEMPERATURE degC
""")


def _write_smv(tmp_path: Path, content: str = SMV_CONTENT) -> Path:
    smv = tmp_path / "room_fire.smv"
    smv.write_text(content, encoding="utf-8")
    return smv


# ─────────────────────────────────────────────────────────────────────────────
# SmvParser integration (via ResultIndex._ingest_smv)
# ─────────────────────────────────────────────────────────────────────────────

class TestSmvEnhancedIndex:

    def test_build_from_smv_returns_result_index(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert isinstance(idx, ResultIndex)

    def test_chid_from_smv(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert idx.chid == "room_fire"

    def test_smv_filepath_stored(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert idx.smv_filepath is not None
        assert "room_fire.smv" in idx.smv_filepath

    def test_smv_metadata_stored(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert idx.smv_metadata is not None

    def test_smv_grids_populated(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert len(idx.smv_grids) >= 1

    def test_smv_devices_populated(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert "TC_01" in idx.smv_devices
        assert "TC_02" in idx.smv_devices

    def test_smv_device_xyz(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        dev = idx.smv_devices.get("TC_01")
        assert dev is not None
        assert abs(dev.x - 2.0) < 0.01
        assert abs(dev.y - 2.0) < 0.01
        assert abs(dev.z - 1.5) < 0.01

    def test_find_smv_device_returns_device(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        dev = idx.find_smv_device("TC_01")
        assert dev is not None

    def test_find_smv_device_missing_returns_none(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert idx.find_smv_device("NONEXISTENT") is None

    def test_device_locations_returns_dict(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        locs = idx.device_locations()
        assert isinstance(locs, dict)
        assert len(locs) >= 2

    def test_slice_index_populated_from_smv(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        # SMV has one SLCF entry
        assert len(idx.slice_index) >= 1

    def test_slice_quantity_from_smv(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        qtys = idx.slice_quantities()
        assert any("TEMPERATURE" in q.upper() for q in qtys)

    def test_boundary_index_populated_from_smv(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert len(idx.boundary_index) >= 1

    def test_build_auto_uses_smv(self, tmp_path):
        """ResultIndex.build() should auto-detect and use the SMV."""
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build(str(tmp_path))
        assert idx.smv_filepath is not None

    def test_build_no_smv_fallback(self, tmp_path):
        """ResultIndex.build() without SMV falls back to directory scan."""
        idx = ResultIndex.build(str(tmp_path))
        assert idx.smv_filepath is None
        assert len(idx.slice_index) == 0  # no .sf files either

    def test_build_use_smv_false_ignores_smv(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build(str(tmp_path), use_smv=False)
        assert idx.smv_filepath is None

    def test_summary_includes_smv_info(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        s = idx.summary()
        assert "SMV" in s or "smv" in s.lower()

    def test_output_dir_set(self, tmp_path):
        smv = _write_smv(tmp_path)
        idx = ResultIndex.build_from_smv(str(smv))
        assert idx.output_dir == str(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# SliceIndex._scan_files()
# ─────────────────────────────────────────────────────────────────────────────

class TestSliceIndexScanFiles:

    def test_scan_files_empty_list(self):
        idx = SliceIndex()
        idx._scan_files([])
        assert len(idx) == 0

    def test_scan_files_skips_missing(self, tmp_path):
        idx = SliceIndex()
        idx._scan_files([tmp_path / "nonexistent.sf"])
        assert len(idx) == 0


# ─────────────────────────────────────────────────────────────────────────────
# BatchStudyConfig validation
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchStudyConfigValidation:

    def _valid_dict(self) -> dict:
        return {
            "name": "test_study",
            "vary": [
                {"path": "params.t_end", "values": [30, 60, 120]},
            ],
        }

    def test_valid_config_parses(self):
        cfg = BatchStudyConfig.from_dict(self._valid_dict())
        assert cfg.name == "test_study"

    def test_missing_name_raises(self):
        d = self._valid_dict()
        del d["name"]
        with pytest.raises(BatchConfigError, match="name"):
            BatchStudyConfig.from_dict(d)

    def test_empty_name_raises(self):
        d = self._valid_dict()
        d["name"] = "  "
        with pytest.raises(BatchConfigError, match="name"):
            BatchStudyConfig.from_dict(d)

    def test_missing_vary_raises(self):
        d = self._valid_dict()
        del d["vary"]
        with pytest.raises(BatchConfigError, match="vary"):
            BatchStudyConfig.from_dict(d)

    def test_empty_vary_raises(self):
        d = self._valid_dict()
        d["vary"] = []
        with pytest.raises(BatchConfigError, match="vary"):
            BatchStudyConfig.from_dict(d)

    def test_vary_missing_path_raises(self):
        d = self._valid_dict()
        d["vary"] = [{"values": [1, 2, 3]}]
        with pytest.raises(BatchConfigError):
            BatchStudyConfig.from_dict(d)

    def test_vary_empty_values_raises(self):
        d = self._valid_dict()
        d["vary"] = [{"path": "params.t_end", "values": []}]
        with pytest.raises(BatchConfigError):
            BatchStudyConfig.from_dict(d)

    def test_invalid_max_workers_raises(self):
        d = self._valid_dict()
        d["max_workers"] = 0
        with pytest.raises(BatchConfigError, match="max_workers"):
            BatchStudyConfig.from_dict(d)

    def test_non_integer_max_workers_raises(self):
        d = self._valid_dict()
        d["max_workers"] = "four"
        with pytest.raises(BatchConfigError, match="max_workers"):
            BatchStudyConfig.from_dict(d)

    def test_non_bool_run_raises(self):
        d = self._valid_dict()
        d["run"] = "yes"
        with pytest.raises(BatchConfigError, match="run"):
            BatchStudyConfig.from_dict(d)

    def test_invalid_fix_raises(self):
        d = self._valid_dict()
        d["fix"] = "not_a_dict"
        with pytest.raises(BatchConfigError, match="fix"):
            BatchStudyConfig.from_dict(d)

    def test_nonexistent_fds_binary_raises(self):
        d = self._valid_dict()
        d["fds_binary"] = "/path/to/nonexistent/fds"
        with pytest.raises(BatchConfigError, match="fds_binary"):
            BatchStudyConfig.from_dict(d)

    def test_empty_fds_binary_ok(self):
        d = self._valid_dict()
        d["fds_binary"] = ""
        cfg = BatchStudyConfig.from_dict(d)
        assert cfg.fds_binary == ""


class TestBatchStudyConfigDefaults:

    def _cfg(self) -> BatchStudyConfig:
        return BatchStudyConfig.from_dict({
            "name": "study",
            "vary": [{"path": "a.b", "values": [1, 2]}],
        })

    def test_default_output_root(self):
        assert self._cfg().output_root == "batch_results"

    def test_default_max_workers(self):
        assert self._cfg().max_workers == 2

    def test_default_run_true(self):
        assert self._cfg().run_simulations is True

    def test_default_fixed_empty(self):
        assert self._cfg().fixed == {}

    def test_default_base_fds_empty(self):
        assert self._cfg().base_fds_file == ""


class TestBatchStudyConfigAxes:

    def test_single_axis(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [{"path": "p.t", "values": [1, 2, 3]}],
        })
        assert len(cfg.axes) == 1
        assert cfg.axes[0].path == "p.t"
        assert cfg.axes[0].values == [1, 2, 3]

    def test_axis_label(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [{"path": "p.t", "values": [1], "label": "T_END"}],
        })
        assert cfg.axes[0].label == "T_END"

    def test_axis_no_label_is_none(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [{"path": "p.t", "values": [1]}],
        })
        assert cfg.axes[0].label is None

    def test_multiple_axes(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [
                {"path": "a", "values": [1, 2]},
                {"path": "b", "values": [10, 20, 30]},
            ],
        })
        assert len(cfg.axes) == 2

    def test_n_variants_single_axis(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [{"path": "a", "values": [1, 2, 3]}],
        })
        assert cfg.n_variants == 3

    def test_n_variants_cartesian(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [
                {"path": "a", "values": [1, 2]},
                {"path": "b", "values": [10, 20, 30]},
            ],
        })
        assert cfg.n_variants == 6


class TestBatchStudyConfigRoundTrip:

    def test_to_dict_round_trip(self):
        original = {
            "name": "sensitivity",
            "base_fds_file": "base.fds",
            "output_root": "results/",
            "max_workers": 4,
            "vary": [
                {"path": "params.t_end", "values": [60, 120], "label": "T_END"},
            ],
            "fix": {"misc.tmpa": 20.0},
            "run": False,
        }
        cfg = BatchStudyConfig.from_dict(original)
        exported = cfg.to_dict()
        cfg2 = BatchStudyConfig.from_dict(exported)
        assert cfg2.name == cfg.name
        assert cfg2.n_variants == cfg.n_variants
        assert cfg2.run_simulations == cfg.run_simulations

    def test_to_json_valid(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [{"path": "a", "values": [1, 2]}],
        })
        text = cfg.to_json()
        data = json.loads(text)
        assert data["name"] == "s"

    def test_from_file(self, tmp_path):
        config_path = tmp_path / "study.json"
        data = {
            "name": "file_test",
            "vary": [{"path": "params.t_end", "values": [30, 60]}],
        }
        config_path.write_text(json.dumps(data), encoding="utf-8")
        cfg = BatchStudyConfig.from_file(str(config_path))
        assert cfg.name == "file_test"
        assert cfg.n_variants == 2

    def test_from_file_missing_raises(self, tmp_path):
        with pytest.raises(BatchConfigError, match="not found"):
            BatchStudyConfig.from_file(str(tmp_path / "nonexistent.json"))

    def test_from_file_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(BatchConfigError, match="JSON"):
            BatchStudyConfig.from_file(str(bad))

    def test_repr(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [{"path": "a", "values": [1, 2]}],
        })
        r = repr(cfg)
        assert "BatchStudyConfig" in r
        assert "s" in r


class TestBatchStudyConfigBuild:

    def test_build_returns_study_and_executor(self):
        from pyfds.execution.batch import ParametricStudy, BatchExecutor
        cfg = BatchStudyConfig.from_dict({
            "name": "s",
            "vary": [{"path": "a", "values": [1]}],
        })
        study, executor = cfg.build()
        assert isinstance(study, ParametricStudy)
        assert isinstance(executor, BatchExecutor)

    def test_build_study_has_correct_name(self):
        cfg = BatchStudyConfig.from_dict({
            "name": "my_study",
            "vary": [{"path": "a", "values": [1]}],
        })
        study, _ = cfg.build()
        assert study.name == "my_study"
