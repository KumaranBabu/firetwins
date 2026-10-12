"""Unit tests — Phase 2 results modules. (part 1 of 1). (part 2 of 3)."""


from __future__ import annotations

import io
import struct
from typing import List
from unittest.mock import MagicMock

import numpy as np
import pytest


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
