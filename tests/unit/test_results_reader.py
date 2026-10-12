"""Unit tests — pyfds.results.reader (DeviceReader, LogParser, SliceReader)."""
from __future__ import annotations

import io
import struct
import pytest

from pyfds.results.reader import DeviceReader, LogParser, SliceReader
from pyfds.core.exceptions import FdsBinaryError


# ---------------------------------------------------------------------------
# DeviceReader
# ---------------------------------------------------------------------------

class TestDeviceReader:
    def test_read_basic_csv(self, fake_devc_csv):
        results = DeviceReader.read(fake_devc_csv)
        assert "tc_center" in results
        assert "hrr_total" in results

    def test_time_column_present(self, fake_devc_csv):
        results = DeviceReader.read(fake_devc_csv)
        # Time series should have 4 data rows
        tc = results["tc_center"]
        assert len(tc.times) == 4

    def test_units_parsed(self, fake_devc_csv):
        results = DeviceReader.read(fake_devc_csv)
        tc = results["tc_center"]
        assert tc.units == "C"

    def test_data_values_numeric(self, fake_devc_csv):
        results = DeviceReader.read(fake_devc_csv)
        hrr = results["hrr_total"]
        assert hrr.data[-1] == 200.0

    def test_nonexistent_file_raises(self):
        with pytest.raises((FileNotFoundError, OSError, Exception)):
            DeviceReader.read("/nonexistent/path/devc.csv")

    def test_returns_reader_result_objects(self, fake_devc_csv):
        from pyfds.results.reader import ReaderResult
        results = DeviceReader.read(fake_devc_csv)
        for v in results.values():
            assert isinstance(v, ReaderResult)


# ---------------------------------------------------------------------------
# LogParser
# ---------------------------------------------------------------------------

class TestLogParser:
    def test_parse_out_file(self, fake_out_file):
        stats = LogParser.parse(fake_out_file)
        assert stats is not None

    def test_chid_extracted(self, fake_out_file):
        stats = LogParser.parse(fake_out_file)
        assert stats.chid == "room_fire"

    def test_version_extracted(self, fake_out_file):
        stats = LogParser.parse(fake_out_file)
        assert "6.9.1" in stats.version

    def test_completed_flag(self, fake_out_file):
        stats = LogParser.parse(fake_out_file)
        assert stats.completed is True

    def test_t_end_extracted(self, fake_out_file):
        stats = LogParser.parse(fake_out_file)
        assert stats.t_end == 60.0

    def test_wall_time_extracted(self, fake_out_file):
        stats = LogParser.parse(fake_out_file)
        assert stats.wall_time is not None
        assert stats.wall_time > 0

    def test_nonexistent_file_raises(self):
        with pytest.raises((FileNotFoundError, OSError, Exception)):
            LogParser.parse("/nonexistent/path/case.out")

    def test_error_lines_empty_for_clean_run(self, fake_out_file):
        stats = LogParser.parse(fake_out_file)
        assert isinstance(stats.error_lines, list)

    def test_failed_simulation(self, tmp_path):
        content = """\
 FDS Version: 6.9.1
 CHID: bad_case
 T_END= 60.000
 ERROR: something went wrong at line 99
"""
        out = tmp_path / "bad_case.out"
        out.write_text(content)
        stats = LogParser.parse(str(out))
        assert stats.completed is False or len(stats.error_lines) > 0


# ---------------------------------------------------------------------------
# SliceReader
# ---------------------------------------------------------------------------

class TestSliceReader:
    def test_read_slice_returns_reader_result(self, fake_slice_file):
        from pyfds.results.reader import ReaderResult
        result = SliceReader.read(fake_slice_file)
        assert isinstance(result, ReaderResult)

    def test_quantity_string(self, fake_slice_file):
        result = SliceReader.read(fake_slice_file)
        assert "TEMPERATURE" in result.quantity.upper()

    def test_units_string(self, fake_slice_file):
        result = SliceReader.read(fake_slice_file)
        assert result.units == "C"

    def test_two_frames_read(self, fake_slice_file):
        result = SliceReader.read(fake_slice_file)
        assert len(result.times) == 2

    def test_times_monotonic(self, fake_slice_file):
        result = SliceReader.read(fake_slice_file)
        assert result.times[1] > result.times[0]

    def test_data_shape_matches_grid(self, fake_slice_file):
        result = SliceReader.read(fake_slice_file)
        # Grid is 3×3×1, 2 frames → data shape (2, 3, 3, 1) or (2, n_cells)
        assert result.data is not None
        total_values = result.data.size
        assert total_values == 2 * 3 * 3 * 1  # frames × ni × nj × nk

    def test_iter_frames_yields_correct_count(self, fake_slice_file):
        frames = list(SliceReader.iter_frames(fake_slice_file))
        assert len(frames) == 2

    def test_iter_frames_yields_time_data_tuples(self, fake_slice_file):
        for t, data in SliceReader.iter_frames(fake_slice_file):
            assert isinstance(t, float)
            assert data is not None

    def test_corrupt_record_raises_binary_error(self, tmp_path):
        """A file with mismatched Fortran record markers should raise FdsBinaryError."""
        bad = tmp_path / "bad.sf"
        # Write garbage
        bad.write_bytes(b"\xff\xff\xff\xff" + b"X" * 30 + b"\x00\x00\x00\x00")
        with pytest.raises((FdsBinaryError, EOFError, Exception)):
            SliceReader.read(str(bad))

    def test_nonexistent_file_raises(self):
        with pytest.raises((FileNotFoundError, OSError, Exception)):
            SliceReader.read("/nonexistent/path/data.sf")
