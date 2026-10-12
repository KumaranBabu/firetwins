"""Unit tests — pyfds.results.report (ReportSection, SimulationReport)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from pyfds.results.report import ReportSection, SimulationReport
from pyfds.results.reader import SimulationStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_stats(**kwargs) -> SimulationStats:
    defaults = dict(
        fds_version="FDS 6.9.0",
        t_end=60.0,
        t_reached=60.0,
        wall_time_seconds=120.0,
        completed=True,
    )
    defaults.update(kwargs)
    return SimulationStats(**defaults)


def _mock_reader_result(data, units="°C"):
    rr = MagicMock()
    rr.data = data
    rr.units = units
    rr.times = None
    return rr


# ---------------------------------------------------------------------------
# ReportSection
# ---------------------------------------------------------------------------

class TestReportSection:
    def test_add_row(self):
        sec = ReportSection("Test")
        sec.add_row("key", "value")
        assert sec.rows == [("key", "value")]

    def test_add_note(self):
        sec = ReportSection("Test")
        sec.add_note("a note")
        assert sec.notes == ["a note"]

    def test_add_row_coerces_to_string(self):
        sec = ReportSection("Test")
        sec.add_row("count", 42)
        assert sec.rows[0] == ("count", "42")

    def test_as_text_contains_title(self):
        sec = ReportSection("My Section")
        text = sec.as_text()
        assert "My Section" in text

    def test_as_text_contains_rows(self):
        sec = ReportSection("S")
        sec.add_row("FDS version", "6.9.0")
        text = sec.as_text()
        assert "FDS version" in text
        assert "6.9.0" in text

    def test_as_text_contains_notes(self):
        sec = ReportSection("S")
        sec.add_note("Important note")
        text = sec.as_text()
        assert "Important note" in text

    def test_as_html_contains_title(self):
        sec = ReportSection("HTML Section")
        html = sec.as_html()
        assert "HTML Section" in html

    def test_as_html_contains_table_rows(self):
        sec = ReportSection("S")
        sec.add_row("key", "val")
        html = sec.as_html()
        assert "<table>" in html
        assert "key" in html
        assert "val" in html

    def test_as_html_contains_notes(self):
        sec = ReportSection("S")
        sec.add_note("note text")
        html = sec.as_html()
        assert "note text" in html

    def test_as_html_escapes_special_chars(self):
        sec = ReportSection("S")
        sec.add_row("a&b", "<value>")
        html = sec.as_html()
        assert "&amp;" in html or "a&amp;b" in html
        assert "&lt;" in html or "&lt;value&gt;" in html


# ---------------------------------------------------------------------------
# SimulationReport — construction
# ---------------------------------------------------------------------------

class TestSimulationReportConstruction:
    def test_default_title(self):
        rpt = SimulationReport()
        assert "Report" in rpt.title

    def test_custom_title(self):
        rpt = SimulationReport(title="Hotel Fire Report")
        assert rpt.title == "Hotel Fire Report"

    def test_repr_no_stats(self):
        rpt = SimulationReport()
        assert "stats=False" in repr(rpt)

    def test_repr_with_stats(self):
        rpt = SimulationReport(stats=_mock_stats())
        assert "stats=True" in repr(rpt)

    def test_repr_device_count(self):
        rpt = SimulationReport(
            device_results={"TC_01": _mock_reader_result([1.0, 2.0])}
        )
        assert "devices=1" in repr(rpt)


# ---------------------------------------------------------------------------
# SimulationReport — as_text
# ---------------------------------------------------------------------------

class TestSimulationReportText:
    def test_as_text_contains_title(self):
        rpt = SimulationReport(title="My Fire")
        text = rpt.as_text()
        assert "My Fire" in text

    def test_as_text_contains_overview(self):
        rpt = SimulationReport()
        text = rpt.as_text()
        assert "Overview" in text

    def test_as_text_with_stats(self):
        rpt = SimulationReport(stats=_mock_stats(fds_version="FDS 6.9.0"))
        text = rpt.as_text()
        assert "6.9.0" in text
        assert "Simulation Statistics" in text

    def test_as_text_incomplete_sim_note(self):
        rpt = SimulationReport(stats=_mock_stats(completed=False))
        text = rpt.as_text()
        assert "partial" in text.lower() or "not complete" in text.lower()

    def test_as_text_with_devices(self):
        rpt = SimulationReport(
            device_results={
                "TC_01": _mock_reader_result([20.0, 25.0, 30.0]),
            }
        )
        text = rpt.as_text()
        assert "TC_01" in text
        assert "Device" in text

    def test_as_text_no_devices_no_device_section(self):
        rpt = SimulationReport()
        text = rpt.as_text()
        assert "Device Summary" not in text

    def test_as_text_time_key_skipped_in_devices(self):
        rpt = SimulationReport(
            device_results={
                "Time": _mock_reader_result([0.0, 1.0]),
                "TC_01": _mock_reader_result([100.0, 110.0]),
            }
        )
        text = rpt.as_text()
        assert "TC_01" in text


# ---------------------------------------------------------------------------
# SimulationReport — as_html
# ---------------------------------------------------------------------------

class TestSimulationReportHtml:
    def test_as_html_is_valid_structure(self):
        rpt = SimulationReport(title="Hotel Fire")
        html = rpt.as_html()
        assert "<!DOCTYPE html>" in html
        assert "<title>" in html
        assert "Hotel Fire" in html

    def test_as_html_contains_sections(self):
        rpt = SimulationReport(stats=_mock_stats())
        html = rpt.as_html()
        assert "<section>" in html

    def test_as_html_escapes_title(self):
        rpt = SimulationReport(title="Fire & Smoke <test>")
        html = rpt.as_html()
        assert "Fire &amp; Smoke" in html or "&amp;" in html


# ---------------------------------------------------------------------------
# SimulationReport — validation section
# ---------------------------------------------------------------------------

class TestSimulationReportValidation:
    def test_validation_no_issues_shows_note(self):
        val = MagicMock()
        val.issues = []
        rpt = SimulationReport(validation_report=val)
        text = rpt.as_text()
        assert "Validation" in text

    def test_validation_issues_included(self):
        issue = MagicMock()
        issue.severity = "ERROR"
        issue.message = "Missing mesh"
        val = MagicMock()
        val.issues = [issue]
        rpt = SimulationReport(validation_report=val)
        text = rpt.as_text()
        assert "Missing mesh" in text

    def test_no_validation_no_section(self):
        rpt = SimulationReport()
        text = rpt.as_text()
        assert "Validation" not in text


# ---------------------------------------------------------------------------
# SimulationReport — add_section and save
# ---------------------------------------------------------------------------

class TestSimulationReportExtra:
    def test_add_extra_section(self):
        rpt = SimulationReport()
        extra = ReportSection("Custom Section")
        extra.add_row("note", "custom value")
        rpt.add_section(extra)
        text = rpt.as_text()
        assert "Custom Section" in text

    def test_save_text(self, tmp_path):
        rpt = SimulationReport(title="Save Test")
        filepath = str(tmp_path / "report.txt")
        rpt.save(filepath, fmt="text")
        content = (tmp_path / "report.txt").read_text()
        assert "Save Test" in content

    def test_save_html(self, tmp_path):
        rpt = SimulationReport(title="Save Test")
        filepath = str(tmp_path / "report.html")
        rpt.save(filepath, fmt="html")
        content = (tmp_path / "report.html").read_text()
        assert "<!DOCTYPE html>" in content
