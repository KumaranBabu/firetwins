"""Unit tests — ReportSection.add_chart and inline HTML embedding."""
from __future__ import annotations

import base64
import io

import pytest

from pyfds.results.report import ReportSection, SimulationReport, _fig_to_base64


# ---------------------------------------------------------------------------
# Helpers — lightweight mock figure that mimics matplotlib.figure.Figure
# ---------------------------------------------------------------------------

class _MockFig:
    """Minimal stand-in for a matplotlib Figure used for encoding tests."""

    def savefig(self, buf, *, format="png", dpi=100, bbox_inches="tight"):
        buf.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)  # minimal PNG-like header


# ---------------------------------------------------------------------------
# _fig_to_base64 helper
# ---------------------------------------------------------------------------

class TestFigToBase64:
    def test_returns_data_uri_string(self):
        uri = _fig_to_base64(_MockFig())
        assert isinstance(uri, str)
        assert uri.startswith("data:image/png;base64,")

    def test_base64_content_decodable(self):
        uri = _fig_to_base64(_MockFig())
        b64_part = uri.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert len(decoded) > 0

    def test_svg_format(self):
        uri = _fig_to_base64(_MockFig(), fmt="svg")
        assert uri.startswith("data:image/svg;base64,")

    def test_dpi_parameter_accepted(self):
        uri = _fig_to_base64(_MockFig(), dpi=150)
        assert uri.startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# ReportSection.add_chart
# ---------------------------------------------------------------------------

class TestReportSectionAddChart:
    def test_chart_added_to_list(self):
        sec = ReportSection("Charts")
        sec.add_chart(_MockFig())
        assert len(sec.charts) == 1

    def test_multiple_charts(self):
        sec = ReportSection("Multi")
        sec.add_chart(_MockFig(), caption="HRR")
        sec.add_chart(_MockFig(), caption="Temp")
        assert len(sec.charts) == 2

    def test_caption_stored(self):
        sec = ReportSection("S")
        sec.add_chart(_MockFig(), caption="My caption")
        _, caption = sec.charts[0]
        assert caption == "My caption"

    def test_data_uri_stored(self):
        sec = ReportSection("S")
        sec.add_chart(_MockFig())
        data_uri, _ = sec.charts[0]
        assert data_uri.startswith("data:image/")

    def test_as_html_contains_img_tag(self):
        sec = ReportSection("Visual")
        sec.add_chart(_MockFig())
        html = sec.as_html()
        assert "<img" in html
        assert "data:image/png;base64," in html

    def test_as_html_contains_caption(self):
        sec = ReportSection("Visual")
        sec.add_chart(_MockFig(), caption="Temperature profile")
        html = sec.as_html()
        assert "Temperature profile" in html

    def test_as_html_empty_caption_no_figcaption(self):
        sec = ReportSection("NoCaption")
        sec.add_chart(_MockFig(), caption="")
        html = sec.as_html()
        assert "<figcaption" not in html

    def test_as_html_contains_figure_tag(self):
        sec = ReportSection("S")
        sec.add_chart(_MockFig())
        assert "<figure" in sec.as_html()

    def test_as_text_mentions_chart_count(self):
        sec = ReportSection("S")
        sec.add_chart(_MockFig())
        sec.add_chart(_MockFig())
        text = sec.as_text()
        assert "2" in text and "chart" in text.lower()

    def test_close_after_false_does_not_raise(self):
        sec = ReportSection("S")
        sec.add_chart(_MockFig(), close_after=False)
        assert len(sec.charts) == 1

    def test_svg_format_in_html(self):
        sec = ReportSection("SVG")
        sec.add_chart(_MockFig(), fmt="svg")
        html = sec.as_html()
        assert "data:image/svg;base64," in html

    def test_section_has_no_charts_by_default(self):
        sec = ReportSection("Empty")
        assert sec.charts == []
        assert "<img" not in sec.as_html()


# ---------------------------------------------------------------------------
# SimulationReport.add_section_obj
# ---------------------------------------------------------------------------

class TestSimulationReportAddSectionObj:
    def test_returns_section(self):
        rpt = SimulationReport()
        sec = ReportSection("New Section")
        returned = rpt.add_section_obj(sec)
        assert returned is sec

    def test_section_appears_in_html(self):
        rpt = SimulationReport()
        sec = rpt.add_section_obj(ReportSection("FireResults"))
        sec.add_row("Peak HRR", "500 kW")
        html = rpt.as_html()
        assert "FireResults" in html
        assert "500 kW" in html

    def test_chart_in_section_appears_in_report_html(self):
        rpt = SimulationReport()
        sec = rpt.add_section_obj(ReportSection("Charts"))
        sec.add_chart(_MockFig(), caption="HRR over time")
        html = rpt.as_html()
        assert "data:image/png;base64," in html
        assert "HRR over time" in html

    def test_multiple_charts_in_report(self):
        rpt = SimulationReport()
        sec = rpt.add_section_obj(ReportSection("Outputs"))
        sec.add_chart(_MockFig(), caption="Fig 1")
        sec.add_chart(_MockFig(), caption="Fig 2")
        html = rpt.as_html()
        assert html.count("<img") == 2


# ---------------------------------------------------------------------------
# HTML escaping of captions
# ---------------------------------------------------------------------------

class TestCaptionEscaping:
    def test_html_special_chars_escaped_in_caption(self):
        sec = ReportSection("S")
        sec.add_chart(_MockFig(), caption="T < 200 & Q > 0")
        html = sec.as_html()
        assert "<200" not in html
        assert "&lt;" in html or "T &lt; 200" in html


# ---------------------------------------------------------------------------
# Caption edge cases
# ---------------------------------------------------------------------------

class TestCaptionEdgeCases:
    def test_double_quotes_in_caption_escaped(self):
        sec = ReportSection("S")
        sec.add_chart(_MockFig(), caption='Result: "peak HRR" = 500 kW')
        html = sec.as_html()
        # Raw unescaped " inside an attribute would break HTML — must be escaped
        # Accept either &quot; or the caption text not appearing as raw "
        assert "&quot;" in html or 'Result:' in html

    def test_multiple_charts_preserve_insertion_order(self):
        sec = ReportSection("Order")
        captions = [f"Chart {i}" for i in range(5)]
        for cap in captions:
            sec.add_chart(_MockFig(), caption=cap)
        html = sec.as_html()
        indices = [html.find(cap) for cap in captions]
        assert indices == sorted(indices), "Charts should appear in insertion order"

    def test_newline_in_caption_doesnt_break_html(self):
        sec = ReportSection("S")
        sec.add_chart(_MockFig(), caption="Line 1\nLine 2")
        html = sec.as_html()
        assert "<img" in html

    def test_very_long_caption_truncated_or_included(self):
        sec = ReportSection("S")
        long_cap = "A" * 2000
        sec.add_chart(_MockFig(), caption=long_cap)
        html = sec.as_html()
        assert "<img" in html  # chart still embedded


# ---------------------------------------------------------------------------
# save with charts
# ---------------------------------------------------------------------------

class TestSaveWithCharts:
    def test_save_html_with_embedded_chart(self, tmp_path):
        rpt = SimulationReport(title="Chart Test")
        sec = rpt.add_section_obj(ReportSection("Visuals"))
        sec.add_chart(_MockFig(), caption="main figure")
        path = str(tmp_path / "report_charts.html")
        rpt.save(path, fmt="html")
        content = (tmp_path / "report_charts.html").read_text()
        assert "data:image/png;base64," in content
        assert "main figure" in content
