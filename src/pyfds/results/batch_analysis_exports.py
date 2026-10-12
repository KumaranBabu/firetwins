"""BatchAnalysisReport: CSV, HTML and JSON export."""
from __future__ import annotations

from typing import TYPE_CHECKING

import logging
import csv
import json
import math
from pathlib import Path

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .batch_analysis import BatchAnalysisReport


class BatchAnalysisReportExportsMixin:
    def to_csv(self, filepath: str) -> None:
        """
        Write two-section CSV:
        1. Per-variant peak matrix  (rows = variants, columns = channels)
        2. Cross-variant statistics (one row per channel)
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        channels = list(self.channel_stats.keys())
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)

            # Section 1: variant peak matrix
            writer.writerow(["# VARIANT PEAK VALUES"])
            header = ["variant_id"] + [f"{ch}_peak" for ch in channels]
            writer.writerow(header)
            for vs in self.variant_summaries:
                row = [vs.variant_id] + [
                    f"{vs.device_peaks.get(ch, float('nan')):.6g}"
                    for ch in channels
                ]
                writer.writerow(row)

            writer.writerow([])
            writer.writerow(["# CROSS-VARIANT STATISTICS"])
            stat_header = [
                "channel", "units", "n_variants",
                "peak_min", "peak_max", "peak_mean", "peak_std", "peak_cov",
                "integral_min", "integral_max", "integral_mean", "integral_std",
                "n_outliers",
            ]
            writer.writerow(stat_header)
            for ch, st in self.channel_stats.items():
                writer.writerow([
                    ch, st.units, st.n_variants,
                    f"{st.peak_min:.6g}", f"{st.peak_max:.6g}",
                    f"{st.peak_mean:.6g}", f"{st.peak_std:.6g}",
                    f"{st.peak_cov:.4f}",
                    f"{st.integral_min:.6g}", f"{st.integral_max:.6g}",
                    f"{st.integral_mean:.6g}", f"{st.integral_std:.6g}",
                    len(st.outlier_variant_ids),
                ])
        logger.info("BatchAnalysisReport: wrote CSV → %s", filepath)

    def to_html(self, filepath: str, title: str = "") -> None:
        """Write a self-contained HTML report with styled tables."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        title = title or f"Batch Analysis: {self.study_name}"

        channels = list(self.channel_stats.keys())
        peak_rows = ""
        for vs in self.variant_summaries:
            cells = "".join(
                f"<td>{vs.device_peaks.get(ch, float('nan')):.4g}</td>"
                for ch in channels
            )
            status = "" if vs.completed else " ⚠"
            peak_rows += f"<tr><td>{vs.variant_id}{status}</td>{cells}</tr>\n"

        peak_headers = "".join(f"<th>{ch}</th>" for ch in channels)

        stat_rows = ""
        for ch, st in self.channel_stats.items():
            outlier_str = ", ".join(st.outlier_variant_ids) or "—"
            stat_rows += (
                f"<tr><td>{ch}</td><td>{st.units}</td>"
                f"<td>{st.peak_min:.4g}</td><td>{st.peak_max:.4g}</td>"
                f"<td>{st.peak_mean:.4g}</td><td>{st.peak_std:.4g}</td>"
                f"<td>{st.peak_cov:.1%}</td>"
                f"<td>{st.integral_mean:.4g}</td>"
                f"<td>{outlier_str}</td></tr>\n"
            )

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: sans-serif; margin: 2em; }}
  h1   {{ color: #2c3e50; }}
  h2   {{ color: #34495e; margin-top: 2em; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1em; font-size: 0.9em; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: right; }}
  th   {{ background: #2c3e50; color: white; text-align: center; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  td:first-child {{ text-align: left; }}
  .meta {{ color: #666; font-size: 0.85em; margin-bottom: 1em; }}
</style>
</head><body>
<h1>{title}</h1>
<p class="meta">Variants: {self.n_variants} &nbsp;|&nbsp;
Completed: {self.n_completed} &nbsp;|&nbsp;
Channels: {len(self.channel_stats)}</p>

<h2>Peak Values by Variant</h2>
<table>
<thead><tr><th>Variant</th>{peak_headers}</tr></thead>
<tbody>
{peak_rows}
</tbody>
</table>

<h2>Cross-Variant Statistics</h2>
<table>
<thead>
<tr>
  <th>Channel</th><th>Units</th>
  <th>Peak min</th><th>Peak max</th><th>Peak mean</th><th>Peak σ</th><th>CoV</th>
  <th>∫ mean</th><th>Outliers (&gt;2σ)</th>
</tr>
</thead>
<tbody>
{stat_rows}
</tbody>
</table>
</body></html>"""
        path.write_text(html, encoding="utf-8")
        logger.info("BatchAnalysisReport: wrote HTML → %s", filepath)

    def to_json(self, filepath: str) -> None:
        data = {
            "study_name":  self.study_name,
            "n_variants":  self.n_variants,
            "n_completed": self.n_completed,
            "channel_stats": {ch: st.as_dict() for ch, st in self.channel_stats.items()},
            "variants": [
                {
                    "id":         vs.variant_id,
                    "completed":  vs.completed,
                    "peaks":      {k: (v if math.isfinite(v) else None)
                                   for k, v in vs.device_peaks.items()},
                    "integrals":  {k: (v if math.isfinite(v) else None)
                                   for k, v in vs.device_integrals.items()},
                }
                for vs in self.variant_summaries
            ],
        }
        Path(filepath).write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("BatchAnalysisReport: wrote JSON → %s", filepath)
