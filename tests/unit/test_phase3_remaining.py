"""
Unit tests — Phase 3 remaining items:
  1. ResultIndex archive/restore (to_dict / from_dict / save / load)
  2. ResultsManager.archive() / restore()
  3. plot_timeseries_interactive()
  4. DB export (export_materials, export_surfaces, export_fuels, export_all)
  5. EngineeringManager export wrappers
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib
matplotlib.use("Agg")   # headless; must be before any pyplot import

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_index():
    """Return a ResultIndex with no files scanned (all defaults)."""
    from pyfds.results.indexer import ResultIndex
    idx = ResultIndex()
    idx.output_dir = "/some/output"
    idx.chid = "test_case"
    idx.plot3d_files = ["/some/output/test_case.q"]
    idx.particle_files = ["/some/output/test_case.prt5"]
    return idx


def _make_mock_api():
    api = MagicMock()
    api.project.chid = "test_case"
    api.config = MagicMock()
    return api


def _make_device_results():
    """Minimal fake device results dict with two channels."""
    import numpy as np
    from pyfds.results.reader import ReaderResult
    t = np.linspace(0, 60, 30)
    return {
        "TC1": ReaderResult(
            source_file="case_devc.csv", quantity="TC1", units="C",
            times=t, data=np.random.uniform(20, 200, 30)
        ),
        "TC2": ReaderResult(
            source_file="case_devc.csv", quantity="TC2", units="C",
            times=t, data=np.random.uniform(20, 200, 30)
        ),
    }


# ===========================================================================
# 1. ResultIndex archive / restore
# ===========================================================================

class TestResultIndexArchive:

    def test_to_dict_returns_dict(self):
        idx = _make_minimal_index()
        d = idx.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_expected_keys(self):
        idx = _make_minimal_index()
        d = idx.to_dict()
        for key in ("output_dir", "chid", "stats", "device_files",
                    "slice_entries", "boundary_entries",
                    "plot3d_files", "particle_files"):
            assert key in d, f"missing key {key!r}"

    def test_to_dict_plot3d_preserved(self):
        idx = _make_minimal_index()
        assert idx.to_dict()["plot3d_files"] == ["/some/output/test_case.q"]

    def test_to_dict_particle_preserved(self):
        idx = _make_minimal_index()
        assert idx.to_dict()["particle_files"] == ["/some/output/test_case.prt5"]

    def test_from_dict_restores_chid(self):
        from pyfds.results.indexer import ResultIndex
        idx = _make_minimal_index()
        d = idx.to_dict()
        restored = ResultIndex.from_dict(d)
        assert restored.chid == "test_case"

    def test_from_dict_restores_output_dir(self):
        from pyfds.results.indexer import ResultIndex
        idx = _make_minimal_index()
        restored = ResultIndex.from_dict(idx.to_dict())
        assert restored.output_dir == "/some/output"

    def test_from_dict_restores_plot3d_files(self):
        from pyfds.results.indexer import ResultIndex
        idx = _make_minimal_index()
        restored = ResultIndex.from_dict(idx.to_dict())
        assert restored.plot3d_files == idx.plot3d_files

    def test_from_dict_restores_particle_files(self):
        from pyfds.results.indexer import ResultIndex
        idx = _make_minimal_index()
        restored = ResultIndex.from_dict(idx.to_dict())
        assert restored.particle_files == idx.particle_files

    def test_from_dict_restores_stats_completed(self):
        from pyfds.results.indexer import ResultIndex
        idx = _make_minimal_index()
        idx.stats.completed = True
        idx.stats.t_reached = 30.0
        restored = ResultIndex.from_dict(idx.to_dict())
        assert restored.stats.completed is True
        assert restored.stats.t_reached == pytest.approx(30.0)

    def test_roundtrip_empty_index(self):
        from pyfds.results.indexer import ResultIndex
        idx = ResultIndex()
        restored = ResultIndex.from_dict(idx.to_dict())
        assert restored.chid == ""
        assert restored.plot3d_files == []
        assert restored.particle_files == []

    def test_save_load_roundtrip(self):
        from pyfds.results.indexer import ResultIndex
        idx = _make_minimal_index()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "index.json")
            idx.save(path)
            assert Path(path).exists()
            restored = ResultIndex.load(path)
        assert restored.chid == "test_case"
        assert restored.plot3d_files == idx.plot3d_files

    def test_save_produces_valid_json(self):
        idx = _make_minimal_index()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "index.json")
            idx.save(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        assert data["chid"] == "test_case"

    def test_load_restores_smv_filepath(self):
        from pyfds.results.indexer import ResultIndex
        idx = _make_minimal_index()
        idx.smv_filepath = "/some/output/test_case.smv"
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "index.json")
            idx.save(path)
            restored = ResultIndex.load(path)
        assert restored.smv_filepath == "/some/output/test_case.smv"


# ===========================================================================
# 2. ResultsManager.archive() / restore()
# ===========================================================================

class TestResultsManagerArchiveRestore:

    def test_archive_without_index_raises(self):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(_make_mock_api())
        with pytest.raises(RuntimeError, match="No index built"):
            with tempfile.TemporaryDirectory() as d:
                mgr.archive(str(Path(d) / "idx.json"))

    def test_archive_restore_roundtrip(self):
        from pyfds.api.controller import ResultsManager
        from pyfds.results.indexer import ResultIndex
        mgr = ResultsManager(_make_mock_api())
        # Manually set index (skip actual file scan)
        mgr._index = _make_minimal_index()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "idx.json")
            mgr.archive(path)
            mgr2 = ResultsManager(_make_mock_api())
            restored = mgr2.restore(path)
        assert isinstance(restored, ResultIndex)
        assert restored.chid == "test_case"

    def test_restore_sets_internal_index(self):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(_make_mock_api())
        mgr._index = _make_minimal_index()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "idx.json")
            mgr.archive(path)
            mgr2 = ResultsManager(_make_mock_api())
            assert mgr2._index is None
            mgr2.restore(path)
            assert mgr2._index is not None

    def test_restore_returns_index_with_correct_plot3d(self):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(_make_mock_api())
        mgr._index = _make_minimal_index()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "idx.json")
            mgr.archive(path)
            mgr2 = ResultsManager(_make_mock_api())
            restored = mgr2.restore(path)
        assert restored.plot3d_files == ["/some/output/test_case.q"]


# ===========================================================================
# 3. plot_timeseries_interactive()
# ===========================================================================

class TestPlotTimeseriesInteractive:

    def test_returns_figure(self):
        import matplotlib.figure
        from pyfds.results.plotters import plot_timeseries_interactive
        results = _make_device_results()
        fig = plot_timeseries_interactive(results)
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_empty_results_returns_figure(self):
        import matplotlib.figure
        from pyfds.results.plotters import plot_timeseries_interactive
        fig = plot_timeseries_interactive({})
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_has_slider_refs(self):
        from pyfds.results.plotters import plot_timeseries_interactive
        results = _make_device_results()
        fig = plot_timeseries_interactive(results)
        assert hasattr(fig, "_pyfds_sliders")
        assert len(fig._pyfds_sliders) == 2

    def test_subset_of_channels(self):
        import matplotlib.figure
        from pyfds.results.plotters import plot_timeseries_interactive
        results = _make_device_results()
        fig = plot_timeseries_interactive(results, device_names=["TC1"])
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_dispatch_interactive_timeseries_kind(self):
        """ResultsManager.plot() dispatches kind='interactive_timeseries'."""
        import matplotlib.figure
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(_make_mock_api())
        results = _make_device_results()
        fig = mgr.plot(results, kind="interactive_timeseries")
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_infer_still_returns_device_timeseries_for_dict(self):
        from pyfds.api.controller import ResultsManager
        mgr = ResultsManager(_make_mock_api())
        assert mgr._infer_plot_kind({}) == "device_timeseries"


# ===========================================================================
# 4. DB Export — export_materials / export_surfaces / export_fuels / export_all
# ===========================================================================

class TestDbExportJson:

    def test_export_materials_json_is_valid(self):
        from pyfds.domain.db_export import export_materials
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "mats.json")
            export_materials(path, fmt="json")
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_export_materials_json_has_concrete(self):
        from pyfds.domain.db_export import export_materials
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "mats.json")
            export_materials(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        assert "concrete" in data

    def test_export_surfaces_json_is_valid(self):
        from pyfds.domain.db_export import export_surfaces
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "surfs.json")
            export_surfaces(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_export_fuels_json_is_valid(self):
        from pyfds.domain.db_export import export_fuels
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "fuels.json")
            export_fuels(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_export_fuels_json_has_methane(self):
        from pyfds.domain.db_export import export_fuels
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "fuels.json")
            export_fuels(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        assert any("methane" in k.lower() for k in data)

    def test_invalid_fmt_raises(self):
        from pyfds.domain.db_export import export_materials
        with pytest.raises(ValueError, match="Unknown format"):
            export_materials("/tmp/x.txt", fmt="xml")

    def test_export_all_writes_three_files(self):
        from pyfds.domain.db_export import export_all
        with tempfile.TemporaryDirectory() as d:
            result = export_all(d, fmt="json")
            assert set(result.keys()) == {"materials", "surfaces", "fuels"}
            for path in result.values():
                assert Path(path).exists()

    def test_export_all_custom_stem(self):
        from pyfds.domain.db_export import export_all
        with tempfile.TemporaryDirectory() as d:
            result = export_all(d, fmt="json", stem="mydb")
            assert Path(result["materials"]).name == "mydb_materials.json"


class TestDbExportCsv:

    def test_export_materials_csv_has_header(self):
        import csv as csv_mod
        from pyfds.domain.db_export import export_materials
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "mats.csv")
            export_materials(path, fmt="csv")
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv_mod.DictReader(fh)
                rows = list(reader)
        assert "name" in reader.fieldnames
        assert len(rows) > 0

    def test_export_surfaces_csv_has_header(self):
        import csv as csv_mod
        from pyfds.domain.db_export import export_surfaces
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "surfs.csv")
            export_surfaces(path, fmt="csv")
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv_mod.DictReader(fh)
                rows = list(reader)
        assert "name" in reader.fieldnames
        assert len(rows) > 0

    def test_export_fuels_csv_has_header(self):
        import csv as csv_mod
        from pyfds.domain.db_export import export_fuels
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "fuels.csv")
            export_fuels(path, fmt="csv")
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv_mod.DictReader(fh)
                rows = list(reader)
        assert "name" in reader.fieldnames
        assert len(rows) > 0

    def test_export_all_csv_three_files(self):
        from pyfds.domain.db_export import export_all
        with tempfile.TemporaryDirectory() as d:
            result = export_all(d, fmt="csv")
            for path in result.values():
                assert Path(path).exists()
                assert path.endswith(".csv")


# ===========================================================================
# 5. EngineeringManager export wrappers
# ===========================================================================

class TestEngineeringManagerExport:

    def _make_api(self):
        from pyfds.api.controller import FdsApi
        return FdsApi()

    def test_export_materials_via_api(self):
        api = self._make_api()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "mats.json")
            api.engineering.export_materials(path)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert isinstance(data, dict) and len(data) > 0

    def test_export_surfaces_via_api(self):
        api = self._make_api()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "surfs.json")
            api.engineering.export_surfaces(path)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert isinstance(data, dict) and len(data) > 0

    def test_export_fuels_via_api(self):
        api = self._make_api()
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "fuels.json")
            api.engineering.export_fuels(path)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert isinstance(data, dict) and len(data) > 0

    def test_export_db_writes_all(self):
        api = self._make_api()
        with tempfile.TemporaryDirectory() as d:
            result = api.engineering.export_db(d)
            assert set(result.keys()) == {"materials", "surfaces", "fuels"}

    def test_export_db_csv(self):
        api = self._make_api()
        with tempfile.TemporaryDirectory() as d:
            result = api.engineering.export_db(d, fmt="csv")
            for path in result.values():
                assert path.endswith(".csv")
