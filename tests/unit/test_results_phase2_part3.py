"""Unit tests — Phase 2 results modules. (part 1 of 1). (part 3 of 3)."""


from __future__ import annotations

import io
import struct
from typing import List
from unittest.mock import MagicMock

import numpy as np
import pytest


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
