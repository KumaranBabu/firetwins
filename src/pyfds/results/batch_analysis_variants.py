"""BatchResultAnalyzer: finding and reading variants, computing statistics."""
from __future__ import annotations

from typing import TYPE_CHECKING

import logging
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from .batch_analysis_stats import ChannelStats, VariantSummary

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .batch_analysis import BatchResultAnalyzer


class BatchResultAnalyzerVariantsMixin:
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
