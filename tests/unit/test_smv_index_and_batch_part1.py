"""Tests for: (part 1 of 1). (part 1 of 3)."""


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

class TestSliceIndexScanFiles:

    def test_scan_files_empty_list(self):
        idx = SliceIndex()
        idx._scan_files([])
        assert len(idx) == 0

    def test_scan_files_skips_missing(self, tmp_path):
        idx = SliceIndex()
        idx._scan_files([tmp_path / "nonexistent.sf"])
        assert len(idx) == 0
