"""
PyFDS Simulation Report
=======================
Generates structured text or HTML summary reports from FDS post-processing data.

Classes
-------
ReportSection       — a named block of key-value rows, paragraphs, and inline charts
SimulationReport    — assembles sections from SimulationStats, validation, and devices

Usage::

    from pyfds.results.report import SimulationReport
    from pyfds.results.reader import LogParser, DeviceReader
    from pyfds.results.plotters import plot_hrr

    stats = LogParser.parse("case.out")
    results = DeviceReader.read("case_devc.csv")

    rpt = SimulationReport(stats=stats, device_results=results)
    sec = rpt.add_section_obj(ReportSection("Fire Curves"))
    fig = plot_hrr(results)
    sec.add_chart(fig, caption="Heat Release Rate")
    rpt.save("report.html", fmt="html")
"""
from __future__ import annotations

import base64
import datetime
import html
import io
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pyfds.results.reader import SimulationStats


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def _fig_to_base64(fig: Any, dpi: int = 100, fmt: str = "png") -> str:
    """Encode a matplotlib Figure to a base64 data-URI string."""
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/{fmt};base64,{b64}"


@dataclass
class ReportSection:
    """One named section in a report."""
    title: str
    rows: List[Tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    # Each entry: (base64_data_uri, caption)
    charts: List[Tuple[str, str]] = field(default_factory=list)

    def add_row(self, label: str, value: Any) -> None:
        self.rows.append((str(label), str(value)))

    def add_note(self, text: str) -> None:
        self.notes.append(text)

    def add_chart(
        self,
        fig: Any,
        caption: str = "",
        *,
        dpi: int = 100,
        fmt: str = "png",
        close_after: bool = False,
    ) -> None:
        """
        Embed a matplotlib Figure inline in the HTML report.

        Parameters
        ----------
        fig : matplotlib.figure.Figure
            The figure to embed.
        caption : str
            Short descriptive text shown below the chart.
        dpi : int
            Render resolution (default 100).
        fmt : str
            Image format: ``"png"`` (default) or ``"svg"``.
        close_after : bool
            If True, call ``plt.close(fig)`` after encoding to free memory.
        """
        data_uri = _fig_to_base64(fig, dpi=dpi, fmt=fmt)
        self.charts.append((data_uri, caption))
        if close_after:
            try:
                import matplotlib.pyplot as plt
                plt.close(fig)
            except Exception:
                pass

    # ── Renderers ────────────────────────────────────────────────────────────

    def as_text(self, *, width: int = 60) -> str:
        lines = [f"{'─' * width}", f"  {self.title}", f"{'─' * width}"]
        for label, value in self.rows:
            lines.append(f"  {label:<28}{value}")
        for note in self.notes:
            lines.append(f"  * {note}")
        if self.charts:
            lines.append(f"  [{len(self.charts)} chart(s) — view HTML report]")
        return "\n".join(lines)

    def as_html(self) -> str:
        parts = [f"<section>", f"  <h2>{html.escape(self.title)}</h2>"]
        if self.rows:
            parts.append("  <table>")
            for label, value in self.rows:
                parts.append(
                    f"    <tr><th>{html.escape(label)}</th>"
                    f"<td>{html.escape(value)}</td></tr>"
                )
            parts.append("  </table>")
        for note in self.notes:
            parts.append(f"  <p class=\"note\">{html.escape(note)}</p>")
        for data_uri, caption in self.charts:
            parts.append(
                f'  <figure style="margin:1em 0;">'
                f'<img src="{data_uri}" style="max-width:100%;border:1px solid #ddd;">'
            )
            if caption:
                parts.append(
                    f'  <figcaption style="font-size:.85em;color:#555;">'
                    f'{html.escape(caption)}</figcaption>'
                )
            parts.append("  </figure>")
        parts.append("</section>")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# SimulationReport
# ---------------------------------------------------------------------------

class SimulationReport:
    """
    Assembles a multi-section report from FDS post-processing artifacts.

    Parameters
    ----------
    stats : SimulationStats, optional
        Parsed from ``LogParser.parse()``.
    validation_report : object, optional
        Duck-typed: if it has ``.issues`` (iterable of objects with
        ``.message`` and ``.severity``), they are included.
    device_results : dict, optional
        Mapping ``device_name → ReaderResult`` from ``DeviceReader.read()``.
    title : str
        Report heading.
    """

    def __init__(
        self,
        *,
        stats: Optional[SimulationStats] = None,
        validation_report: Optional[Any] = None,
        device_results: Optional[Dict[str, Any]] = None,
        title: str = "FDS Simulation Report",
    ) -> None:
        self.title = title
        self._stats = stats
        self._validation = validation_report
        self._devices = device_results or {}
        self._extra_sections: List[ReportSection] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def add_section(self, section: ReportSection) -> None:
        """Append a custom section to the report."""
        self._extra_sections.append(section)

    def add_section_obj(self, section: ReportSection) -> ReportSection:
        """Append *section* and return it for chaining / chart embedding."""
        self._extra_sections.append(section)
        return section

    # ── Section builders ──────────────────────────────────────────────────────

    def _build_overview(self) -> ReportSection:
        sec = ReportSection("Overview")
        sec.add_row("Report generated", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        sec.add_row("Report title", self.title)
        return sec

    def _build_stats(self) -> Optional[ReportSection]:
        if self._stats is None:
            return None
        s = self._stats
        sec = ReportSection("Simulation Statistics")
        sec.add_row("FDS version", s.fds_version or "unknown")
        sec.add_row("Simulation time (s)", f"{s.t_end:.1f}")
        sec.add_row("Time reached (s)", f"{s.t_reached:.1f}")
        sec.add_row("Wall-clock time (s)", f"{s.wall_time_seconds:.1f}")
        completed_str = "Yes" if s.completed else "No"
        sec.add_row("Completed successfully", completed_str)
        if not s.completed:
            sec.add_note("Simulation did not complete — results may be partial.")
        return sec

    def _build_validation(self) -> Optional[ReportSection]:
        if self._validation is None:
            return None
        issues = getattr(self._validation, "issues", None)
        if not issues:
            sec = ReportSection("Validation")
            sec.add_note("No validation issues found.")
            return sec
        sec = ReportSection("Validation Issues")
        for issue in issues:
            severity = getattr(issue, "severity", "INFO")
            message  = getattr(issue, "message", str(issue))
            sec.add_row(str(severity), message)
        return sec

    def _build_devices(self) -> Optional[ReportSection]:
        if not self._devices:
            return None
        sec = ReportSection("Device Summary")
        for name, rr in self._devices.items():
            if name.lower() == "time":
                continue
            units = getattr(rr, "units", "") or ""
            data  = getattr(rr, "data", None)
            times = getattr(rr, "times", None)
            if data is not None and len(data) > 0:
                import numpy as np
                min_v  = float(np.nanmin(data))
                max_v  = float(np.nanmax(data))
                n_pts  = len(data)
                label  = f"{name} ({units})" if units else name
                sec.add_row(label, f"n={n_pts}  min={min_v:.3g}  max={max_v:.3g}")
            else:
                sec.add_row(name, "no data")
        return sec

    def _all_sections(self) -> List[ReportSection]:
        secs: List[ReportSection] = [self._build_overview()]
        stats_sec = self._build_stats()
        if stats_sec:
            secs.append(stats_sec)
        val_sec = self._build_validation()
        if val_sec:
            secs.append(val_sec)
        dev_sec = self._build_devices()
        if dev_sec:
            secs.append(dev_sec)
        secs.extend(self._extra_sections)
        return secs

    # ── Renderers ─────────────────────────────────────────────────────────────

    def as_text(self, *, width: int = 60) -> str:
        header = [
            "=" * width,
            f"  {self.title}",
            "=" * width,
            "",
        ]
        body = []
        for sec in self._all_sections():
            body.append(sec.as_text(width=width))
            body.append("")
        return "\n".join(header + body)

    def as_html(self) -> str:
        escaped_title = html.escape(self.title)
        sections_html = "\n".join(sec.as_html() for sec in self._all_sections())
        return (
            "<!DOCTYPE html>\n"
            "<html lang=\"en\">\n"
            "<head>\n"
            "  <meta charset=\"UTF-8\">\n"
            f"  <title>{escaped_title}</title>\n"
            "  <style>\n"
            "    body { font-family: sans-serif; margin: 2em; }\n"
            "    h1   { border-bottom: 2px solid #333; padding-bottom: .3em; }\n"
            "    h2   { margin-top: 1.5em; color: #444; }\n"
            "    table { border-collapse: collapse; width: 100%; }\n"
            "    th, td { text-align: left; padding: .3em .6em; "
            "border: 1px solid #ccc; }\n"
            "    th   { background: #f0f0f0; width: 35%; }\n"
            "    .note { color: #c00; font-style: italic; }\n"
            "    figure img { display: block; }\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            f"<h1>{escaped_title}</h1>\n"
            f"{sections_html}\n"
            "</body>\n"
            "</html>"
        )

    def save(self, filepath: str, *, fmt: str = "text") -> None:
        """
        Write the report to *filepath*.

        Parameters
        ----------
        filepath : str
            Output path.
        fmt : {"text", "html"}
            Format to write.
        """
        content = self.as_html() if fmt == "html" else self.as_text()
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(content)

    def __repr__(self) -> str:
        has_stats = self._stats is not None
        n_devs = len([k for k in self._devices if k.lower() != "time"])
        return f"<SimulationReport title={self.title!r} stats={has_stats} devices={n_devs}>"
