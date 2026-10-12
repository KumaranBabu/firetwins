"""
PyFDS Batch Result Analyzer
============================
Post-process a completed parametric study: discover variant directories,
read device time-series from each run, compute cross-variant statistics,
flag outliers, and export results to CSV or HTML.

Typical usage::

    from pyfds.results.batch_analysis import BatchResultAnalyzer

    analyzer = BatchResultAnalyzer("batch_results/hrr_sensitivity")
    report   = analyzer.analyze()
    print(report.summary())
    report.to_csv("batch_summary.csv")
    report.to_html("batch_report.html")
"""
from __future__ import annotations

import csv
import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class VariantSummary:
    """Per-variant result snapshot."""
    variant_id: str
    axis_values: Dict[str, Any]         # {dot-path → value}
    device_peaks:     Dict[str, float]  # channel → peak value
    device_means:     Dict[str, float]  # channel → time-mean
    device_integrals: Dict[str, float]  # channel → ∫ value dt
    device_units:     Dict[str, str]    # channel → units string
    completed: bool = True
    error: Optional[str] = None

    def peak(self, channel: str) -> Optional[float]:
        return self.device_peaks.get(channel)


@dataclass
class ChannelStats:
    """Cross-variant statistics for one device channel."""
    channel: str
    units: str
    n_variants: int

    peak_min:  float = 0.0
    peak_max:  float = 0.0
    peak_mean: float = 0.0
    peak_std:  float = 0.0

    integral_min:  float = 0.0
    integral_max:  float = 0.0
    integral_mean: float = 0.0
    integral_std:  float = 0.0

    outlier_variant_ids: List[str] = field(default_factory=list)

    @property
    def peak_cov(self) -> float:
        """Coefficient of variation for peak values (0 → 1)."""
        return (self.peak_std / self.peak_mean) if self.peak_mean else 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "channel":       self.channel,
            "units":         self.units,
            "n_variants":    self.n_variants,
            "peak_min":      self.peak_min,
            "peak_max":      self.peak_max,
            "peak_mean":     self.peak_mean,
            "peak_std":      self.peak_std,
            "peak_cov":      round(self.peak_cov, 4),
            "integral_min":  self.integral_min,
            "integral_max":  self.integral_max,
            "integral_mean": self.integral_mean,
            "integral_std":  self.integral_std,
            "outliers":      self.outlier_variant_ids,
        }


@dataclass
class BatchAnalysisReport:
    """
    Full batch post-processing output.

    Attributes
    ----------
    study_name : str
        Taken from the output root directory name.
    n_variants : int
        Total variants discovered.
    n_completed : int
        Variants with at least one device CSV.
    variant_summaries : list[VariantSummary]
        Per-variant results.
    channel_stats : dict[str, ChannelStats]
        Cross-variant statistics keyed by device/channel name.
    """
    study_name: str
    n_variants: int
    n_completed: int
    variant_summaries: List[VariantSummary] = field(default_factory=list)
    channel_stats: Dict[str, ChannelStats]  = field(default_factory=dict)

    # ── Text summary ──────────────────────────────────────────────────────────

    def summary(self) -> str:
        lines = [
            f"Batch Analysis: {self.study_name}",
            f"  Variants : {self.n_variants}  (completed: {self.n_completed})",
            f"  Channels : {len(self.channel_stats)}",
        ]
        if self.channel_stats:
            lines.append("")
            lines.append(f"  {'Channel':<30} {'Peak mean':>12} {'Peak std':>10} {'CoV':>7}  Outliers")
            lines.append("  " + "-" * 68)
            for ch, st in self.channel_stats.items():
                lines.append(
                    f"  {ch:<30} {st.peak_mean:>12.3g} {st.peak_std:>10.3g} "
                    f"{st.peak_cov:>7.2%}  {len(st.outlier_variant_ids)}"
                )
        return "\n".join(lines)

    # ── CSV export ────────────────────────────────────────────────────────────

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

    # ── HTML export ───────────────────────────────────────────────────────────

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

    # ── JSON export ───────────────────────────────────────────────────────────

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

    def __repr__(self) -> str:
        return (f"<BatchAnalysisReport study={self.study_name!r} "
                f"variants={self.n_variants} channels={len(self.channel_stats)}>")


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class BatchResultAnalyzer:
    """
    Discover and analyze results from a completed parametric study.

    Parameters
    ----------
    output_root : str or Path
        Directory that contains one sub-folder per variant.  When
        ``BatchExecutor`` runs a study named ``"hrr_sens"``, variants land in
        ``<output_root>/hrr_sens/hrr_sens_t_end=30/`` etc.  Pass either the
        study-level directory (``batch_results/hrr_sens``) or the root above
        it (``batch_results``) and supply ``study_name``.
    study_name : str, optional
        If given, the analyzer descends into ``<output_root>/<study_name>/``.
    outlier_sigma : float
        Number of standard deviations from the mean to flag as an outlier.
        Default 2.0.
    """

    def __init__(
        self,
        output_root: str,
        study_name: Optional[str] = None,
        *,
        outlier_sigma: float = 2.0,
    ) -> None:
        root = Path(output_root)
        if study_name:
            self._study_dir = root / study_name
            self._study_name = study_name
        else:
            self._study_dir = root
            self._study_name = root.name
        self._outlier_sigma = outlier_sigma

    # ── Public ────────────────────────────────────────────────────────────────

    def analyze(self) -> BatchAnalysisReport:
        """
        Scan variant directories, read device results, compute statistics.

        Returns a fully populated :class:`BatchAnalysisReport`.
        """
        variant_dirs = self._discover_variants()
        logger.info("BatchResultAnalyzer: found %d variant dirs in %s",
                    len(variant_dirs), self._study_dir)

        summaries: List[VariantSummary] = []
        for vdir in variant_dirs:
            vs = self._read_variant(vdir)
            summaries.append(vs)

        n_completed = sum(1 for vs in summaries if vs.completed)
        stats = self._compute_stats(summaries)

        return BatchAnalysisReport(
            study_name=self._study_name,
            n_variants=len(summaries),
            n_completed=n_completed,
            variant_summaries=summaries,
            channel_stats=stats,
        )

    # ── Discovery ─────────────────────────────────────────────────────────────

    def _discover_variants(self) -> List[Path]:
        """Return sorted list of subdirectories inside the study directory."""
        if not self._study_dir.exists():
            logger.warning("BatchResultAnalyzer: study dir not found: %s",
                           self._study_dir)
            return []
        dirs = sorted(
            p for p in self._study_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
        return dirs

    # ── Per-variant reading ───────────────────────────────────────────────────

    def _read_variant(self, variant_dir: Path) -> VariantSummary:
        """Read device CSVs from one variant directory."""
        variant_id = variant_dir.name

        # Parse axis values from directory name (e.g. "study_p_t=30_hrr=500")
        axis_values = self._parse_axis_values(variant_id)

        # Find all *_devc.csv files in this directory
        csv_files = list(variant_dir.glob("*_devc.csv"))
        if not csv_files:
            # Also try plain *.csv (no _devc suffix)
            csv_files = list(variant_dir.glob("*.csv"))

        if not csv_files:
            return VariantSummary(
                variant_id=variant_id,
                axis_values=axis_values,
                device_peaks={}, device_means={}, device_integrals={},
                device_units={},
                completed=False,
                error="no device CSV found",
            )

        peaks: Dict[str, float] = {}
        means: Dict[str, float] = {}
        integrals: Dict[str, float] = {}
        units_map: Dict[str, str] = {}

        from pyfds.results.reader import DeviceReader
        for csv_path in csv_files:
            try:
                data = DeviceReader.read(str(csv_path))
            except Exception as exc:
                logger.warning("BatchResultAnalyzer: cannot read %s: %s",
                               csv_path.name, exc)
                continue

            for channel, rr in data.items():
                if channel.lower() == "time":
                    continue
                times = rr.times if rr.times is not None else np.array([])
                vals  = rr.data  if rr.data  is not None else np.array([])
                if len(vals) == 0:
                    continue

                units_map[channel] = rr.units
                peak = float(np.max(np.abs(vals)))
                mean = float(np.mean(vals))
                integral = float(np.trapezoid(vals, times)) if len(times) == len(vals) else float(np.sum(vals))

                peaks[channel]     = peak
                means[channel]     = mean
                integrals[channel] = integral

        return VariantSummary(
            variant_id=variant_id,
            axis_values=axis_values,
            device_peaks=peaks,
            device_means=means,
            device_integrals=integrals,
            device_units=units_map,
            completed=bool(peaks),
            error=None if peaks else "empty device data",
        )

    # ── Statistics ────────────────────────────────────────────────────────────

    def _compute_stats(
        self, summaries: List[VariantSummary]
    ) -> Dict[str, ChannelStats]:
        """Compute cross-variant mean/std/outliers for every channel."""
        # Collect all channel names present in any completed variant
        all_channels: Dict[str, str] = {}  # channel → units
        for vs in summaries:
            if vs.completed:
                for ch, u in vs.device_units.items():
                    all_channels.setdefault(ch, u)

        stats: Dict[str, ChannelStats] = {}
        for channel, units in all_channels.items():
            peaks     = []
            integrals = []
            ids       = []
            for vs in summaries:
                if vs.completed and channel in vs.device_peaks:
                    peaks.append(vs.device_peaks[channel])
                    integrals.append(vs.device_integrals.get(channel, 0.0))
                    ids.append(vs.variant_id)

            if not peaks:
                continue

            arr_p = np.array(peaks,     dtype=float)
            arr_i = np.array(integrals, dtype=float)

            p_mean = float(np.mean(arr_p))
            p_std  = float(np.std(arr_p, ddof=0))
            i_mean = float(np.mean(arr_i))
            i_std  = float(np.std(arr_i, ddof=0))

            threshold = p_mean + self._outlier_sigma * p_std
            outliers = [
                vid for vid, p in zip(ids, peaks)
                if p > threshold and p_std > 0
            ]

            stats[channel] = ChannelStats(
                channel=channel,
                units=units,
                n_variants=len(peaks),
                peak_min=float(np.min(arr_p)),
                peak_max=float(np.max(arr_p)),
                peak_mean=p_mean,
                peak_std=p_std,
                integral_min=float(np.min(arr_i)),
                integral_max=float(np.max(arr_i)),
                integral_mean=i_mean,
                integral_std=i_std,
                outlier_variant_ids=outliers,
            )

        return stats

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_axis_values(variant_id: str) -> Dict[str, Any]:
        """
        Extract axis values from a variant directory name.

        E.g. ``"study_p_t_end=30_hrr=500"`` → ``{"t_end": 30.0, "hrr": 500.0}``
        """
        result: Dict[str, Any] = {}
        for part in variant_id.split("_"):
            if "=" in part:
                k, _, v = part.partition("=")
                try:
                    result[k] = float(v)
                except ValueError:
                    result[k] = v
        return result
