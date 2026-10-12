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

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .batch_analysis_exports import (  # noqa: F401  (re-exported)
    BatchAnalysisReportExportsMixin,
)
from .batch_analysis_variants import (  # noqa: F401  (re-exported)
    BatchResultAnalyzerVariantsMixin,
)
from .batch_analysis_stats import (  # noqa: F401  (re-exported)
    ChannelStats,
    VariantSummary,
)


logger = logging.getLogger(__name__)


@dataclass
class BatchAnalysisReport(BatchAnalysisReportExportsMixin):
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

    def __repr__(self) -> str:
        return (f"<BatchAnalysisReport study={self.study_name!r} "
                f"variants={self.n_variants} channels={len(self.channel_stats)}>")


class BatchResultAnalyzer(BatchResultAnalyzerVariantsMixin):
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
