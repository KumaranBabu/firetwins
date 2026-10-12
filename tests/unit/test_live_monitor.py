"""Unit tests — pyfds.execution.runner.LiveMonitor."""
from __future__ import annotations

import time
import threading
from pathlib import Path

import pytest

from pyfds.execution.runner import LiveMonitor, _is_numeric


# ---------------------------------------------------------------------------
# _is_numeric helper
# ---------------------------------------------------------------------------

class TestIsNumeric:
    def test_integer_string(self):
        assert _is_numeric("42")

    def test_float_string(self):
        assert _is_numeric("3.14")

    def test_negative(self):
        assert _is_numeric("-1.5")

    def test_scientific(self):
        assert _is_numeric("1.2e-3")

    def test_empty_string(self):
        assert not _is_numeric("")

    def test_text(self):
        assert not _is_numeric("Time")

    def test_none(self):
        assert not _is_numeric(None)


# ---------------------------------------------------------------------------
# LiveMonitor — no files
# ---------------------------------------------------------------------------

class TestLiveMonitorNoFiles:
    def test_start_stop_no_crash(self, tmp_path):
        m = LiveMonitor(str(tmp_path), "case01", poll_interval=0.05)
        m.start()
        time.sleep(0.12)
        m.stop()
        assert not m.is_running

    def test_hrr_data_empty_when_no_file(self, tmp_path):
        m = LiveMonitor(str(tmp_path), "case01", poll_interval=0.05)
        m.start()
        time.sleep(0.12)
        m.stop()
        assert m.hrr_data == []

    def test_device_data_empty_when_no_file(self, tmp_path):
        m = LiveMonitor(str(tmp_path), "case01", poll_interval=0.05)
        m.start()
        time.sleep(0.12)
        m.stop()
        assert m.device_data == {}


# ---------------------------------------------------------------------------
# LiveMonitor — HRR CSV reading
# ---------------------------------------------------------------------------

class TestHrrReading:
    def _write_hrr(self, path: Path, rows):
        lines = ["Time, HRR, Q_ACTUAL"]
        for t, hrr in rows:
            lines.append(f"{t}, {hrr}, {hrr * 0.9}")
        path.write_text("\n".join(lines))

    def test_reads_hrr_data(self, tmp_path):
        hrr_file = tmp_path / "case_hrr.csv"
        self._write_hrr(hrr_file, [(0.0, 0.0), (1.0, 100.0), (2.0, 200.0)])

        m = LiveMonitor(str(tmp_path), "case", poll_interval=0.05)
        m.start()
        time.sleep(0.25)
        m.stop()

        assert len(m.hrr_data) == 3

    def test_hrr_values_correct(self, tmp_path):
        hrr_file = tmp_path / "mycase_hrr.csv"
        self._write_hrr(hrr_file, [(0.0, 50.0), (1.0, 150.0)])

        m = LiveMonitor(str(tmp_path), "mycase", poll_interval=0.05)
        m.start()
        time.sleep(0.25)
        m.stop()

        times  = [d[0] for d in m.hrr_data]
        values = [d[1] for d in m.hrr_data]
        assert 0.0 in times
        assert 50.0 in values

    def test_on_hrr_callback_called(self, tmp_path):
        hrr_file = tmp_path / "cb_hrr.csv"
        self._write_hrr(hrr_file, [(0.0, 10.0), (1.0, 20.0)])

        received = []
        m = LiveMonitor(str(tmp_path), "cb",
                        poll_interval=0.05,
                        on_hrr=lambda t, h: received.append((t, h)))
        m.start()
        time.sleep(0.25)
        m.stop()

        assert len(received) >= 2

    def test_hrr_incremental_append(self, tmp_path):
        hrr_file = tmp_path / "inc_hrr.csv"
        # Write 2 rows initially
        hrr_file.write_text("Time, HRR\n0.0, 10.0\n1.0, 20.0\n")

        m = LiveMonitor(str(tmp_path), "inc", poll_interval=0.05)
        m.start()
        time.sleep(0.15)

        # Append 1 more row while monitor is running
        with open(hrr_file, "a") as fh:
            fh.write("2.0, 30.0\n")

        time.sleep(0.15)
        m.stop()

        assert len(m.hrr_data) == 3

    def test_malformed_line_skipped(self, tmp_path):
        hrr_file = tmp_path / "bad_hrr.csv"
        hrr_file.write_text("Time, HRR\n0.0, 100.0\nBAD LINE\n1.0, 200.0\n")

        m = LiveMonitor(str(tmp_path), "bad", poll_interval=0.05)
        m.start()
        time.sleep(0.20)
        m.stop()

        assert len(m.hrr_data) == 2  # only the 2 valid rows


# ---------------------------------------------------------------------------
# LiveMonitor — device CSV reading
# ---------------------------------------------------------------------------

class TestDevcReading:
    def _write_devc(self, path: Path, header, rows):
        lines = [",".join(header)]
        for row in rows:
            lines.append(",".join(str(v) for v in row))
        path.write_text("\n".join(lines))

    def test_reads_device_data(self, tmp_path):
        devc_file = tmp_path / "case_devc.csv"
        self._write_devc(devc_file,
                         ["Time", "TC_01", "TC_02"],
                         [(0.0, 20.0, 21.0), (1.0, 25.0, 26.0)])

        m = LiveMonitor(str(tmp_path), "case", poll_interval=0.05)
        m.start()
        time.sleep(0.25)
        m.stop()

        assert "TC_01" in m.device_data
        assert len(m.device_data["TC_01"]) == 2

    def test_on_devices_callback_called(self, tmp_path):
        devc_file = tmp_path / "cb2_devc.csv"
        self._write_devc(devc_file,
                         ["Time", "HRR"],
                         [(0.0, 0.0), (1.0, 100.0)])

        received = []
        m = LiveMonitor(str(tmp_path), "cb2",
                        poll_interval=0.05,
                        on_devices=lambda t, d: received.append(d))
        m.start()
        time.sleep(0.25)
        m.stop()

        assert len(received) >= 2

    def test_header_with_no_data_rows(self, tmp_path):
        devc_file = tmp_path / "nodata_devc.csv"
        devc_file.write_text("Time,TC_01\n")

        m = LiveMonitor(str(tmp_path), "nodata", poll_interval=0.05)
        m.start()
        time.sleep(0.15)
        m.stop()

        assert m.device_data == {}

    def test_no_crash_on_partial_line(self, tmp_path):
        devc_file = tmp_path / "partial_devc.csv"
        devc_file.write_text("Time,TC_01\n0.0,20.0\n1.0")  # partial last line

        m = LiveMonitor(str(tmp_path), "partial", poll_interval=0.05)
        m.start()
        time.sleep(0.20)
        m.stop()
        # At minimum the first complete row should be captured
        assert len(m.device_data.get("TC_01", [])) >= 1


# ---------------------------------------------------------------------------
# LiveMonitor — CSV format variants
# ---------------------------------------------------------------------------

class TestHrrCsvVariants:
    def test_no_space_after_comma_in_header(self, tmp_path):
        """Header without spaces: "Time,HRR" (not "Time, HRR")."""
        hrr_file = tmp_path / "ns_hrr.csv"
        hrr_file.write_text("Time,HRR\n0.0,100.0\n1.0,200.0\n")

        m = LiveMonitor(str(tmp_path), "ns", poll_interval=0.05)
        m.start()
        time.sleep(0.25)
        m.stop()

        assert len(m.hrr_data) == 2

    def test_empty_hrr_column_row_skipped(self, tmp_path):
        """Row with empty HRR value is skipped; valid rows still captured."""
        hrr_file = tmp_path / "ec_hrr.csv"
        hrr_file.write_text("Time, HRR\n0.0, 50.0\n1.0, \n2.0, 150.0\n")

        m = LiveMonitor(str(tmp_path), "ec", poll_interval=0.05)
        m.start()
        time.sleep(0.25)
        m.stop()

        assert len(m.hrr_data) == 2
        assert any(abs(v - 50.0) < 1e-6 for _, v in m.hrr_data)
        assert any(abs(v - 150.0) < 1e-6 for _, v in m.hrr_data)

    def test_binary_garbage_in_hrr_file_no_crash(self, tmp_path):
        hrr_file = tmp_path / "bin_hrr.csv"
        hrr_file.write_bytes(b"Time, HRR\n0.0, 10.0\n\xff\xfe\x00binary\xff\n1.0, 20.0\n")

        m = LiveMonitor(str(tmp_path), "bin", poll_interval=0.05)
        m.start()
        time.sleep(0.25)
        m.stop()

        # At least the two valid rows should be captured
        assert len(m.hrr_data) >= 2

    def test_on_hrr_callback_raises_does_not_stop_monitor(self, tmp_path):
        """Callback raising ValueError is caught; monitor keeps polling."""
        hrr_file = tmp_path / "exc_hrr.csv"
        hrr_file.write_text("Time, HRR\n0.0, 10.0\n1.0, 20.0\n2.0, 30.0\n")

        call_count = [0]

        def bad_callback(t, h):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("deliberate test error")

        m = LiveMonitor(str(tmp_path), "exc", poll_interval=0.05,
                        on_hrr=bad_callback)
        m.start()
        time.sleep(0.30)
        m.stop()

        # Monitor survived; data was appended (append happens before callback)
        assert len(m.hrr_data) >= 2

    def test_devc_quoted_column_names_parsed(self, tmp_path):
        """Column names wrapped in double-quotes are stripped correctly."""
        devc_file = tmp_path / "q_devc.csv"
        devc_file.write_text('"Time","TC_01","TC_02"\n0.0,22.0,23.0\n1.0,25.0,26.0\n')

        m = LiveMonitor(str(tmp_path), "q", poll_interval=0.05)
        m.start()
        time.sleep(0.25)
        m.stop()

        assert "TC_01" in m.device_data
        assert len(m.device_data["TC_01"]) == 2


# ---------------------------------------------------------------------------
# LiveMonitor — is_running
# ---------------------------------------------------------------------------

class TestIsRunning:
    def test_not_running_before_start(self, tmp_path):
        m = LiveMonitor(str(tmp_path), "x")
        assert not m.is_running

    def test_running_after_start(self, tmp_path):
        m = LiveMonitor(str(tmp_path), "x", poll_interval=0.1)
        m.start()
        assert m.is_running
        m.stop()

    def test_not_running_after_stop(self, tmp_path):
        m = LiveMonitor(str(tmp_path), "x", poll_interval=0.05)
        m.start()
        m.stop()
        assert not m.is_running
