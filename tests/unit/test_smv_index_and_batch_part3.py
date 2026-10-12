"""Tests for: (part 1 of 1). (part 3 of 3)."""


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
