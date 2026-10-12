"""Tests for: (part 1 of 1). (part 2 of 3)."""


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
