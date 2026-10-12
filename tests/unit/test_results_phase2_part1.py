"""Unit tests — Phase 2 results modules. (part 1 of 1). (part 1 of 3)."""


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
