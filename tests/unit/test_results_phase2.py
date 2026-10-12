"""
Unit tests — Phase 2 results modules.

Covers:
  - Plot3DReader / Plot3DResult
  - ParticleReader / ParticleResult / ParticleClass / ParticleFrame
  - plotters (smoke tests — verify Figure objects returned, no visual check)
  - SimulationReport / ReportSection
"""
from __future__ import annotations

import io
import struct
from typing import List
from unittest.mock import MagicMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers — Fortran binary record construction
# ---------------------------------------------------------------------------

def _fr(data: bytes) -> bytes:
    """Wrap bytes in a Fortran unformatted record."""
    n = struct.pack("<i", len(data))
    return n + data + n


def _str30(s: str) -> bytes:
    """Encode s as a 30-char padded ASCII string (not wrapped in record)."""
    return s.encode("ascii").ljust(30)[:30]


def _str_record(s: str) -> bytes:
    """Single 30-char string wrapped in Fortran record."""
    return _fr(_str30(s))


def _str_block_record(strings: List[str]) -> bytes:
    """Multiple 30-char strings concatenated and wrapped in one record."""
    return _fr(b"".join(_str30(s) for s in strings))


# ---------------------------------------------------------------------------
# Fixtures — .q (Plot3D) binary
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_plot3d_file(tmp_path):
    """
    Minimal valid FDS Plot3D .q binary with:
      - 2 quantities: TEMPERATURE, PRESSURE
      - mesh 3×3×2
      - 3 time frames
    """
    quantities = ["TEMPERATURE", "PRESSURE"]
    units      = ["C", "Pa"]
    n_qty      = len(quantities)
    ni, nj, nk = 3, 3, 2
    n_values   = ni * nj * nk
    frame_times = [0.0, 1.0, 2.0]

    buf = io.BytesIO()

    # Header
    buf.write(_fr(struct.pack("<i", n_qty)))          # record 1: n_quantities
    buf.write(_str_block_record(quantities))           # record 2: quantity names
    buf.write(_str_block_record(units))                # record 3: units
    buf.write(_fr(struct.pack("<3i", ni, nj, nk)))     # record 4: dims

    # Frames
    for t in frame_times:
        buf.write(_fr(struct.pack("<f", t)))           # time record
        vals = np.arange(n_qty * n_values, dtype=np.float32) + t
        buf.write(_fr(vals.tobytes()))                 # data record (C-order OK for test)

    path = tmp_path / "case_01.q"
    path.write_bytes(buf.getvalue())
    return str(path)


# ---------------------------------------------------------------------------
# Fixtures — .prt5 (Particle) binary
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_prt5_file(tmp_path):
    """
    Minimal valid FDS .prt5 binary with:
      - 1 particle class: "DROPLETS"
      - 1 quantity per class: "DIAMETER"
      - 2 time frames, 4 particles each
    """
    chid       = "test_case"
    cls_name   = "DROPLETS"
    qty_names  = ["DIAMETER"]
    qty_units  = ["m"]
    n_classes  = 1
    n_qty      = 1
    n_particles = 4
    frame_times = [0.0, 1.0]

    buf = io.BytesIO()

    # File header
    buf.write(_str_record(chid))                            # CHID
    buf.write(_fr(struct.pack("<i", n_classes)))            # N_PART (class count)

    # Class header
    buf.write(_str_record(cls_name))                        # class name
    buf.write(_fr(struct.pack("<i", n_qty)))                # n_quantities
    buf.write(_str_block_record(qty_names))                 # quantity names
    buf.write(_str_block_record(qty_units))                 # units

    # Frames
    for t in frame_times:
        # frame header: time (float32) + counts (1 × int32)
        buf.write(_fr(struct.pack("<f", t) + struct.pack("<i", n_particles)))

        # X, Y, Z position records
        xs = np.array([0.0, 0.1, 0.2, 0.3], dtype=np.float32)
        ys = np.array([0.0, 0.1, 0.2, 0.3], dtype=np.float32)
        zs = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
        buf.write(_fr(xs.tobytes()))
        buf.write(_fr(ys.tobytes()))
        buf.write(_fr(zs.tobytes()))

        # Tag record (int32)
        tags = np.array([1, 2, 3, 4], dtype=np.int32)
        buf.write(_fr(tags.tobytes()))

        # Quantity values
        diams = np.full(n_particles, 0.001 * (t + 1), dtype=np.float32)
        buf.write(_fr(diams.tobytes()))

    path = tmp_path / "case.prt5"
    path.write_bytes(buf.getvalue())
    return str(path)


# ---------------------------------------------------------------------------
# TestPlot3DReader
# ---------------------------------------------------------------------------

class TestPlot3DReader:

    def test_read_returns_plot3d_result(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader, Plot3DResult
        result = Plot3DReader.read(fake_plot3d_file)
        assert isinstance(result, Plot3DResult)

    def test_quantities_parsed(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert "TEMPERATURE" in result.quantities
        assert "PRESSURE" in result.quantities

    def test_units_parsed(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert result.units[0] == "C"
        assert result.units[1] == "Pa"

    def test_shape_correct(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert result.shape == (3, 3, 2)

    def test_n_frames(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert result.n_frames == 3

    def test_times_monotonic(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert list(result.times) == [0.0, 1.0, 2.0]

    def test_data_shape(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        # (n_frames, n_qty, ni, nj, nk)
        assert result.data.shape == (3, 2, 3, 3, 2)

    def test_n_quantities_property(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert result.n_quantities == 2

    def test_quantity_index(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert result.quantity_index("TEMPERATURE") == 0
        assert result.quantity_index("PRESSURE") == 1
        assert result.quantity_index("MISSING") is None

    def test_get_quantity(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        temp = result.get_quantity("TEMPERATURE")
        assert temp is not None
        assert temp.shape == (3, 3, 3, 2)  # (n_frames, ni, nj, nk)

    def test_get_quantity_missing_returns_none(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert result.get_quantity("VELOCITY") is None

    def test_frame_method(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        f = result.frame(0)
        assert f.shape == (2, 3, 3, 2)

    def test_iter_frames_yields_pairs(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        frames = list(Plot3DReader.iter_frames(fake_plot3d_file))
        assert len(frames) == 3
        for t, arr in frames:
            assert isinstance(t, float)
            assert arr.shape == (2, 3, 3, 2)

    def test_nonexistent_file_raises(self):
        from pyfds.results.plot3d_reader import Plot3DReader
        with pytest.raises((FileNotFoundError, OSError)):
            Plot3DReader.read("/no/such/file.q")

    def test_source_file_stored(self, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        result = Plot3DReader.read(fake_plot3d_file)
        assert fake_plot3d_file in result.source_file or result.source_file != ""


# ---------------------------------------------------------------------------
# TestParticleReader
# ---------------------------------------------------------------------------

class TestParticleReader:

    def test_read_returns_particle_result(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader, ParticleResult
        result = ParticleReader.read(fake_prt5_file)
        assert isinstance(result, ParticleResult)

    def test_n_classes(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        assert result.n_classes == 1

    def test_class_name(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        assert result.classes[0].name == "DROPLETS"

    def test_class_quantity_names(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        assert "DIAMETER" in result.classes[0].quantity_names

    def test_n_frames(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        cls = result.classes[0]
        assert cls.n_frames == 2

    def test_frame_times(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        cls = result.classes[0]
        times = cls.times
        assert float(times[0]) == pytest.approx(0.0, abs=1e-5)
        assert float(times[1]) == pytest.approx(1.0, abs=1e-5)

    def test_positions_shape(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        frame = result.classes[0].frames[0]
        assert frame.positions.shape == (4, 3)

    def test_n_particles(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        frame = result.classes[0].frames[0]
        assert frame.n_particles == 4

    def test_tags_shape(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        frame = result.classes[0].frames[0]
        assert frame.tags.shape == (4,)

    def test_quantity_data_present(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        frame = result.classes[0].frames[0]
        assert "DIAMETER" in frame.quantities
        assert len(frame.quantities["DIAMETER"]) == 4

    def test_get_class_by_name(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        cls = result.get_class("DROP")
        assert cls is not None
        assert "DROPLETS" in cls.name

    def test_get_class_missing_returns_none(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        assert result.get_class("NONEXISTENT") is None

    def test_nonexistent_file_raises(self):
        from pyfds.results.particle_reader import ParticleReader
        with pytest.raises((FileNotFoundError, OSError)):
            ParticleReader.read("/no/such/file.prt5")

    def test_chid_stored(self, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        result = ParticleReader.read(fake_prt5_file)
        assert result.chid == "test_case"


# ---------------------------------------------------------------------------
# TestPlotters — smoke tests (verify Figure returned, no rendering)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_matplotlib(monkeypatch):
    """Provide a real matplotlib Figure if available, else skip."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        pytest.skip("matplotlib not installed")


class TestPlotters:

    def test_plot_device_timeseries_returns_figure(self, mock_matplotlib, fake_devc_csv):
        from pyfds.results.reader import DeviceReader
        from pyfds.results.plotters import plot_device_timeseries
        results = DeviceReader.read(fake_devc_csv)
        fig = plot_device_timeseries(results, ["tc_center"])
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_device_timeseries_all_devices(self, mock_matplotlib, fake_devc_csv):
        from pyfds.results.reader import DeviceReader
        from pyfds.results.plotters import plot_device_timeseries
        results = DeviceReader.read(fake_devc_csv)
        fig = plot_device_timeseries(results)
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_hrr_returns_figure(self, mock_matplotlib, fake_devc_csv):
        from pyfds.results.reader import DeviceReader
        from pyfds.results.plotters import plot_hrr
        results = DeviceReader.read(fake_devc_csv)
        fig = plot_hrr(results, hrr_key="hrr_total")
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_hrr_no_hrr_key_graceful(self, mock_matplotlib, fake_devc_csv):
        from pyfds.results.reader import DeviceReader
        from pyfds.results.plotters import plot_hrr
        results = DeviceReader.read(fake_devc_csv)
        fig = plot_hrr(results, hrr_key="NONEXISTENT_HRR_KEY")
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_slice_contour_returns_figure(self, mock_matplotlib, fake_slice_file):
        from pyfds.results.reader import SliceReader
        from pyfds.results.plotters import plot_slice_contour
        result = SliceReader.read(fake_slice_file)
        fig = plot_slice_contour(result, frame_index=0)
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_multi_quantity_returns_figure(self, mock_matplotlib, fake_plot3d_file):
        from pyfds.results.plot3d_reader import Plot3DReader
        from pyfds.results.plotters import plot_multi_quantity
        result = Plot3DReader.read(fake_plot3d_file)
        fig = plot_multi_quantity(result, frame_index=0)
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_particle_positions_returns_figure(self, mock_matplotlib, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        from pyfds.results.plotters import plot_particle_positions
        result = ParticleReader.read(fake_prt5_file)
        cls = result.classes[0]
        fig = plot_particle_positions(cls, frame_index=0)
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_particle_positions_with_color_quantity(self, mock_matplotlib, fake_prt5_file):
        from pyfds.results.particle_reader import ParticleReader
        from pyfds.results.plotters import plot_particle_positions
        result = ParticleReader.read(fake_prt5_file)
        cls = result.classes[0]
        fig = plot_particle_positions(cls, frame_index=0, color_quantity="DIAMETER")
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_device_timeseries_missing_device_skipped(self, mock_matplotlib, fake_devc_csv):
        from pyfds.results.reader import DeviceReader
        from pyfds.results.plotters import plot_device_timeseries
        results = DeviceReader.read(fake_devc_csv)
        # Should not raise — missing device is warned and skipped
        fig = plot_device_timeseries(results, ["tc_center", "no_such_device"])
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)

    def test_plot_multi_quantity_empty_result(self, mock_matplotlib):
        from pyfds.results.plotters import plot_multi_quantity
        mock_result = MagicMock()
        mock_result.n_quantities = 0
        fig = plot_multi_quantity(mock_result)
        import matplotlib.figure
        assert isinstance(fig, matplotlib.figure.Figure)


# ---------------------------------------------------------------------------
# TestSimulationReport
# ---------------------------------------------------------------------------

class TestReportSection:

    def test_add_row_and_text(self):
        from pyfds.results.report import ReportSection
        sec = ReportSection("Test Section")
        sec.add_row("FDS version", "6.9.1")
        sec.add_note("Check this value.")
        text = sec.as_text()
        assert "Test Section" in text
        assert "6.9.1" in text
        assert "Check this value." in text

    def test_html_escaping(self):
        from pyfds.results.report import ReportSection
        sec = ReportSection("Safe <Section>")
        sec.add_row("key", "<value>")
        h = sec.as_html()
        assert "&lt;Section&gt;" in h
        assert "&lt;value&gt;" in h

    def test_as_html_has_table(self):
        from pyfds.results.report import ReportSection
        sec = ReportSection("Stats")
        sec.add_row("A", "1")
        h = sec.as_html()
        assert "<table>" in h
        assert "<th>" in h


class TestSimulationReport:

    @pytest.fixture
    def stats(self):
        from pyfds.results.reader import SimulationStats
        return SimulationStats(
            chid="test_case",
            fds_version="6.9.1",
            t_end=60.0,
            t_reached=60.0,
            wall_time_seconds=12.34,
            completed=True,
        )

    def test_repr_shows_title(self, stats):
        from pyfds.results.report import SimulationReport
        rpt = SimulationReport(stats=stats, title="My Report")
        assert "My Report" in repr(rpt)

    def test_as_text_contains_title(self, stats):
        from pyfds.results.report import SimulationReport
        rpt = SimulationReport(stats=stats, title="Room Fire")
        text = rpt.as_text()
        assert "Room Fire" in text

    def test_as_text_contains_stats(self, stats):
        from pyfds.results.report import SimulationReport
        rpt = SimulationReport(stats=stats)
        text = rpt.as_text()
        assert "6.9.1" in text
        assert "60" in text

    def test_completed_yes_in_report(self, stats):
        from pyfds.results.report import SimulationReport
        rpt = SimulationReport(stats=stats)
        text = rpt.as_text()
        assert "Yes" in text

    def test_incomplete_simulation_note(self):
        from pyfds.results.report import SimulationReport
        from pyfds.results.reader import SimulationStats
        s = SimulationStats(completed=False, t_end=60.0, t_reached=30.0)
        rpt = SimulationReport(stats=s)
        text = rpt.as_text()
        assert "partial" in text.lower() or "No" in text

    def test_as_html_is_valid_structure(self, stats):
        from pyfds.results.report import SimulationReport
        rpt = SimulationReport(stats=stats, title="HTML Test")
        h = rpt.as_html()
        assert "<!DOCTYPE html>" in h
        assert "<html" in h
        assert "HTML Test" in h
        assert "</html>" in h

    def test_device_summary_included(self, stats, fake_devc_csv):
        from pyfds.results.reader import DeviceReader
        from pyfds.results.report import SimulationReport
        results = DeviceReader.read(fake_devc_csv)
        rpt = SimulationReport(stats=stats, device_results=results)
        text = rpt.as_text()
        assert "tc_center" in text

    def test_validation_report_duck_typed(self, stats):
        from pyfds.results.report import SimulationReport
        issue = MagicMock()
        issue.severity = "WARNING"
        issue.message = "Mesh aspect ratio exceeds 5:1"
        val = MagicMock()
        val.issues = [issue]
        rpt = SimulationReport(stats=stats, validation_report=val)
        text = rpt.as_text()
        assert "Mesh aspect ratio" in text

    def test_no_issues_shows_clean_note(self, stats):
        from pyfds.results.report import SimulationReport
        val = MagicMock()
        val.issues = []
        rpt = SimulationReport(stats=stats, validation_report=val)
        text = rpt.as_text()
        assert "No validation issues" in text

    def test_add_custom_section(self, stats):
        from pyfds.results.report import SimulationReport, ReportSection
        sec = ReportSection("Custom")
        sec.add_row("peak_temp", "850 C")
        rpt = SimulationReport(stats=stats)
        rpt.add_section(sec)
        text = rpt.as_text()
        assert "Custom" in text
        assert "850 C" in text

    def test_save_text_file(self, stats, tmp_path):
        from pyfds.results.report import SimulationReport
        rpt = SimulationReport(stats=stats, title="SaveTest")
        out = tmp_path / "report.txt"
        rpt.save(str(out), fmt="text")
        content = out.read_text(encoding="utf-8")
        assert "SaveTest" in content

    def test_save_html_file(self, stats, tmp_path):
        from pyfds.results.report import SimulationReport
        rpt = SimulationReport(stats=stats, title="HTMLSave")
        out = tmp_path / "report.html"
        rpt.save(str(out), fmt="html")
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "HTMLSave" in content

    def test_no_stats_report_still_renders(self):
        from pyfds.results.report import SimulationReport
        rpt = SimulationReport()
        text = rpt.as_text()
        assert isinstance(text, str)
        assert len(text) > 0
