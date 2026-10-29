"""
PyFDS SimulationComparator
==========================
Domain-level comparison engine for FDS result sets.

Unlike the CLI ``pyfds compare`` command (which is a thin reporting wrapper),
this module provides a fully typed API suitable for use by automated test
harnesses, parametric study pipelines, and AI agent evaluation loops.

Usage::

    from pyfds.results.comparator import SimulationComparator

    cmp = SimulationComparator("baseline/", "variant/")
    report = cmp.compare(threshold_pct=5.0)
    for ch in report.channels:
        print(ch.name, ch.peak_pct_diff, ch.status)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class ChannelComparison:
    """Comparison result for a single device channel."""
    name: str
    units: str
    baseline_peak: float
    variant_peak: float
    peak_pct_diff: float          # (variant - baseline) / |baseline| * 100
    baseline_mean: float
    variant_mean: float
    mean_pct_diff: float
    threshold_pct: float
    status: str                   # "ok" | "warning" | "missing_baseline" | "missing_variant"
    note: str = ""


@dataclass
class ComparisonReport:
    """Full comparison report across all channels."""
    baseline_dir: str
    variant_dir: str
    threshold_pct: float
    channels: List[ChannelComparison] = field(default_factory=list)

    @property
    def n_ok(self) -> int:
        return sum(1 for c in self.channels if c.status == "ok")

    @property
    def n_warnings(self) -> int:
        return sum(1 for c in self.channels if c.status == "warning")

    @property
    def n_missing(self) -> int:
        return sum(1 for c in self.channels if c.status.startswith("missing"))

    @property
    def passed(self) -> bool:
        return self.n_warnings == 0 and self.n_missing == 0

    def summary(self) -> str:
        lines = [
            f"Comparison: {self.baseline_dir} vs {self.variant_dir}",
            f"Threshold: {self.threshold_pct:.1f}%",
            f"Channels: {len(self.channels)} total  "
            f"({self.n_ok} ok, {self.n_warnings} warnings, {self.n_missing} missing)",
        ]
        for ch in self.channels:
            marker = "OK" if ch.status == "ok" else "!!"
            lines.append(
                f"  [{marker}] {ch.name:<30s}  peak_diff={ch.peak_pct_diff:+.1f}%  "
                f"mean_diff={ch.mean_pct_diff:+.1f}%  status={ch.status}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------

class SimulationComparator:
    """
    Compare two FDS result directories channel-by-channel.

    The comparator reads all ``*_devc.csv`` files from each directory.
    Channels present in one directory but not the other are flagged as
    ``missing_baseline`` or ``missing_variant`` respectively.

    Parameters
    ----------
    baseline_dir:
        Path to the baseline result directory.
    variant_dir:
        Path to the variant (new / modified) result directory.
    """

    def __init__(self, baseline_dir: str, variant_dir: str) -> None:
        self._base = Path(baseline_dir)
        self._var  = Path(variant_dir)

    # ── Public API ─────────────────────────────────────────────────────────

    def compare(self, threshold_pct: float = 5.0) -> ComparisonReport:
        """
        Run the comparison and return a :class:`ComparisonReport`.

        Parameters
        ----------
        threshold_pct:
            Percentage difference above which a channel is flagged as
            ``"warning"`` (default 5 %).
        """
        base_data = self._load_all(self._base)
        var_data  = self._load_all(self._var)

        all_channels = sorted((set(base_data) | set(var_data)) - {"Time"})
        channels: List[ChannelComparison] = []

        for name in all_channels:
            b = base_data.get(name)
            v = var_data.get(name)
            ch = self._compare_channel(name, b, v, threshold_pct)
            channels.append(ch)

        return ComparisonReport(
            baseline_dir=str(self._base),
            variant_dir=str(self._var),
            threshold_pct=threshold_pct,
            channels=channels,
        )

    def channel_names(self) -> Tuple[List[str], List[str]]:
        """Return ``(baseline_channels, variant_channels)`` name lists."""
        base = [k for k in self._load_all(self._base) if k != "Time"]
        var  = [k for k in self._load_all(self._var)  if k != "Time"]
        return base, var

    # ── Internals ──────────────────────────────────────────────────────────

    def _load_all(self, directory: Path) -> Dict[str, "ReaderResult"]:
        from pyfds.results.reader import DeviceReader
        combined: Dict[str, "ReaderResult"] = {}
        csv_files = sorted(directory.glob("*_devc.csv"))
        if not csv_files:
            logger.warning("No *_devc.csv files found in %s", directory)
            return combined
        for csv_path in csv_files:
            try:
                results = DeviceReader.read(str(csv_path))
                combined.update(results)
            except Exception as exc:
                logger.warning("SimulationComparator: could not read %s: %s", csv_path, exc)
        return combined

    @staticmethod
    def _compare_channel(
        name: str,
        baseline: Optional[object],
        variant: Optional[object],
        threshold_pct: float,
    ) -> ChannelComparison:
        nan = float("nan")

        def stats(result: object) -> Tuple[float, float]:
            arr = np.asarray(getattr(result, "data", []), dtype=float)
            return (float(np.max(np.abs(arr))), float(np.mean(arr))) if arr.size else (nan, nan)

        if baseline is None or variant is None:          # the run that has the channel keeps its numbers
            present = variant if baseline is None else baseline
            peak, mean = stats(present)
            side = "baseline" if baseline is None else "variant"
            return ChannelComparison(
                name=name, units=getattr(present, "units", ""),
                baseline_peak=nan if baseline is None else peak, variant_peak=peak if baseline is None else nan,
                peak_pct_diff=nan,
                baseline_mean=nan if baseline is None else mean, variant_mean=mean if baseline is None else nan,
                mean_pct_diff=nan,
                threshold_pct=threshold_pct,
                status=f"missing_{side}",
                note=f"Channel not found in {side} directory.",
            )

        b_arr = np.asarray(getattr(baseline, "data", []), dtype=float)
        v_arr = np.asarray(getattr(variant,  "data", []), dtype=float)
        units = getattr(baseline, "units", "")

        def _safe_pct(new: float, ref: float) -> float:
            if ref == 0.0:
                return 0.0 if new == 0.0 else float("inf")
            return (new - ref) / abs(ref) * 100.0

        b_peak = float(np.max(np.abs(b_arr))) if b_arr.size else 0.0
        v_peak = float(np.max(np.abs(v_arr))) if v_arr.size else 0.0
        b_mean = float(np.mean(b_arr)) if b_arr.size else 0.0
        v_mean = float(np.mean(v_arr)) if v_arr.size else 0.0

        peak_diff = _safe_pct(v_peak, b_peak)
        mean_diff = _safe_pct(v_mean, b_mean)

        if abs(peak_diff) <= threshold_pct:
            status = "ok"
            note = ""
        else:
            status = "warning"
            note = (
                f"Peak differs by {peak_diff:+.1f}% (threshold {threshold_pct:.1f}%)."
            )

        return ChannelComparison(
            name=name, units=units,
            baseline_peak=b_peak, variant_peak=v_peak, peak_pct_diff=peak_diff,
            baseline_mean=b_mean, variant_mean=v_mean, mean_pct_diff=mean_diff,
            threshold_pct=threshold_pct,
            status=status,
            note=note,
        )
