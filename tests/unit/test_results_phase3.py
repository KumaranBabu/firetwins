"""
Unit tests — Phase 3: ResultIndex extensions + ResultsManager API facade.

Covers:
  - ResultIndex auto-detection of *.q and *.prt5 files
  - ResultIndex.find_plot3d() / find_particles() queries
  - ResultIndex.summary() includes new file counts
  - ResultsManager.read_plot3d()
  - ResultsManager.read_particles()
  - ResultsManager.plot() dispatch (auto and explicit kind)
  - ResultsManager.generate_report()
"""
from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers — minimal valid binary files (reused from phase 2 helpers)
# ---------------------------------------------------------------------------

def _fr(data: bytes) -> bytes:
    n = struct.pack("<i", len(data))
    return n + data + n


def _str30(s: str) -> bytes:
    return s.encode("ascii").ljust(30)[:30]


def _str_record(s: str) -> bytes:
    return _fr(_str30(s))


def _str_block_record(strings: List[str]) -> bytes:
    return _fr(b"".join(_str30(s) for s in strings))


def _make_plot3d(path: Path) -> None:
    """Write a minimal valid FDS *.q binary."""
    quantities = ["TEMPERATURE"]
    units = ["C"]
    ni, nj, nk = 2, 2, 2
    buf = io.BytesIO()
    buf.write(_fr(struct.pack("<i", 1)))
    buf.write(_str_block_record(quantities))
    buf.write(_str_block_record(units))
    buf.write(_fr(struct.pack("<3i", ni, nj, nk)))
    buf.write(_fr(struct.pack("<f", 0.0)))
    vals = np.zeros(1 * ni * nj * nk, dtype=np.float32)
    buf.write(_fr(vals.tobytes()))
    path.write_bytes(buf.getvalue())


def _make_prt5(path: Path) -> None:
    """Write a minimal valid FDS *.prt5 binary."""
    buf = io.BytesIO()
    buf.write(_str_record("test_case"))
    buf.write(_fr(struct.pack("<i", 1)))           # 1 class
    buf.write(_str_record("DROPLETS"))
    buf.write(_fr(struct.pack("<i", 1)))           # 1 quantity
    buf.write(_str_block_record(["DIAMETER"]))
    buf.write(_str_block_record(["m"]))
    # 1 frame, 2 particles
    buf.write(_fr(struct.pack("<f", 0.0) + struct.pack("<i", 2)))
    for arr in [
        np.array([0.0, 0.1], dtype=np.float32),
        np.array([0.0, 0.1], dtype=np.float32),
        np.array([0.5, 0.5], dtype=np.float32),
    ]:
        buf.write(_fr(arr.tobytes()))
    buf.write(_fr(np.array([1, 2], dtype=np.int32).tobytes()))
    buf.write(_fr(np.full(2, 0.001, dtype=np.float32).tobytes()))
    path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def output_dir_with_files(tmp_path):
    """A temp dir with one .q and one .prt5 file (no .sf/.bf/.out)."""
    _make_plot3d(tmp_path / "case_01.q")
    _make_prt5(tmp_path / "case_01.prt5")
    return tmp_path


@pytest.fixture
def empty_output_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mock_api():
    api = MagicMock()
    api.project.chid = "test_case"
    api.config = MagicMock()
    return api


# ---------------------------------------------------------------------------
# TestResultIndexPhase3
# ---------------------------------------------------------------------------

class TestResultIndexPhase3:

    def test_build_finds_plot3d_files(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        assert len(idx.plot3d_files) == 1
        assert idx.plot3d_files[0].endswith(".q")

    def test_build_finds_particle_files(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        assert len(idx.particle_files) == 1
        assert idx.particle_files[0].endswith(".prt5")

    def test_find_plot3d_returns_list(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        result = idx.find_plot3d()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_find_particles_returns_list(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        result = idx.find_particles()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_find_plot3d_is_copy(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        lst = idx.find_plot3d()
        lst.append("garbage")
        assert len(idx.plot3d_files) == 1

    def test_empty_dir_has_no_plot3d(self, empty_output_dir):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(empty_output_dir))
        assert idx.find_plot3d() == []

    def test_empty_dir_has_no_particles(self, empty_output_dir):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(empty_output_dir))
        assert idx.find_particles() == []

    def test_summary_includes_plot3d_count(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        s = idx.summary()
        assert "Plot3D" in s
        assert "1" in s

    def test_summary_includes_particle_count(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        s = idx.summary()
        assert "Part" in s

    def test_repr_includes_plot3d(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        r = repr(idx)
        assert "plot3d=1" in r

    def test_repr_includes_particles(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files))
        r = repr(idx)
        assert "particles=1" in r

    def test_index_plot3d_false_skips_scan(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files), index_plot3d=False)
        assert idx.plot3d_files == []

    def test_index_particles_false_skips_scan(self, output_dir_with_files):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex.build(str(output_dir_with_files), index_particles=False)
        assert idx.particle_files == []

    def test_multiple_plot3d_files_all_found(self, tmp_path):
        from pyfds.results.indexer import ResultIndex
        _make_plot3d(tmp_path / "a.q")
        _make_plot3d(tmp_path / "b.q")
        idx = ResultIndex.build(str(tmp_path))
        assert len(idx.plot3d_files) == 2

    def test_multiple_particle_files_all_found(self, tmp_path):
        from pyfds.results.indexer import ResultIndex
        _make_prt5(tmp_path / "a.prt5")
        _make_prt5(tmp_path / "b.prt5")
        idx = ResultIndex.build(str(tmp_path))
        assert len(idx.particle_files) == 2


# ---------------------------------------------------------------------------
# TestResultsManagerPhase3
# ---------------------------------------------------------------------------

class TestResultsManagerPhase3:

    def _make_manager(self, mock_api):
        from pyfds.api.controller import ResultsManager
        return ResultsManager(mock_api)

    def test_read_plot3d_explicit_path(self, mock_api, tmp_path):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.plot3d_reader import Plot3DResult
        q_path = tmp_path / "case.q"
        _make_plot3d(q_path)
        mgr = ResultsManager(mock_api)
        result = mgr.read_plot3d(str(q_path))
        assert isinstance(result, Plot3DResult)

    def test_read_plot3d_no_index_returns_none(self, mock_api):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(mock_api)
        assert mgr.read_plot3d() is None

    def test_read_plot3d_via_index(self, mock_api, output_dir_with_files):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.plot3d_reader import Plot3DResult
        mgr = ResultsManager(mock_api)
        mgr.build_index(str(output_dir_with_files))
        result = mgr.read_plot3d()
        assert isinstance(result, Plot3DResult)

    def test_read_particles_explicit_path(self, mock_api, tmp_path):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.particle_reader import ParticleResult
        prt_path = tmp_path / "case.prt5"
        _make_prt5(prt_path)
        mgr = ResultsManager(mock_api)
        result = mgr.read_particles(str(prt_path))
        assert isinstance(result, ParticleResult)

    def test_read_particles_no_index_returns_none(self, mock_api):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(mock_api)
        assert mgr.read_particles() is None

    def test_read_particles_via_index(self, mock_api, output_dir_with_files):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.particle_reader import ParticleResult
        mgr = ResultsManager(mock_api)
        mgr.build_index(str(output_dir_with_files))
        result = mgr.read_particles()
        assert isinstance(result, ParticleResult)

    def test_plot_dict_infers_device_timeseries(self, mock_api):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(mock_api)
        assert mgr._infer_plot_kind({}) == "device_timeseries"

    def test_plot_plot3d_result_infers_multi_quantity(self, mock_api, tmp_path):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.plot3d_reader import Plot3DReader
        q_path = tmp_path / "case.q"
        _make_plot3d(q_path)
        result = Plot3DReader.read(str(q_path))
        mgr = ResultsManager(mock_api)
        assert mgr._infer_plot_kind(result) == "multi_quantity"

    def test_plot_particle_class_infers_particle_positions(self, mock_api, tmp_path):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.particle_reader import ParticleReader
        prt_path = tmp_path / "case.prt5"
        _make_prt5(prt_path)
        result = ParticleReader.read(str(prt_path))
        cls = result.classes[0]
        mgr = ResultsManager(mock_api)
        assert mgr._infer_plot_kind(cls) == "particle_positions"

    def test_plot_explicit_kind_override(self, mock_api):
        """Explicit kind overrides auto-detection — mock matplotlib to verify dispatch."""
        from pyfds.api.controller import ResultsManager
        import pyfds.results.plotters as plotters_mod
        called_with = {}

        def fake_plot_hrr(result, **kw):
            called_with["fn"] = "plot_hrr"
            called_with["result"] = result
            return MagicMock()

        original = plotters_mod.plot_hrr
        plotters_mod.plot_hrr = fake_plot_hrr
        try:
            mgr = ResultsManager(mock_api)
            dummy = {"HRR": MagicMock()}
            mgr.plot(dummy, kind="hrr")
            assert called_with["fn"] == "plot_hrr"
        finally:
            plotters_mod.plot_hrr = original

    def test_plot_invalid_kind_raises_value_error(self, mock_api):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(mock_api)
        with pytest.raises(ValueError, match="Unknown plot kind"):
            mgr.plot({}, kind="not_a_real_kind")

    def test_generate_report_returns_simulation_report(self, mock_api):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.report import SimulationReport
        mgr = ResultsManager(mock_api)
        rpt = mgr.generate_report()
        assert isinstance(rpt, SimulationReport)

    def test_generate_report_uses_index_stats(self, mock_api, output_dir_with_files):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(mock_api)
        mgr.build_index(str(output_dir_with_files))
        rpt = mgr.generate_report(title="Phase3 Report")
        text = rpt.as_text()
        assert "Phase3 Report" in text

    def test_generate_report_no_index_still_renders(self, mock_api):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(mock_api)
        rpt = mgr.generate_report()
        text = rpt.as_text()
        assert isinstance(text, str) and len(text) > 0

    def test_generate_report_with_device_results(self, mock_api):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.report import SimulationReport
        mgr = ResultsManager(mock_api)
        fake_dev = MagicMock()
        rpt = mgr.generate_report(device_results={"TC1": fake_dev})
        assert isinstance(rpt, SimulationReport)

    def test_generate_report_with_validation(self, mock_api):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.report import SimulationReport
        mgr = ResultsManager(mock_api)
        val = MagicMock()
        val.issues = []
        rpt = mgr.generate_report(validation_report=val)
        assert isinstance(rpt, SimulationReport)
        assert "No validation issues" in rpt.as_text()
