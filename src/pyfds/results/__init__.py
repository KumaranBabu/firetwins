"""PyFDS Results Layer — post-processing readers, plotters, and data indexer."""
from .reader import DeviceReader, LogParser, SliceReader, BoundaryReader, ReaderResult
from .indexer import ResultIndex, SliceIndex, BoundaryIndex
from .plot3d_reader import Plot3DReader, Plot3DResult
from .particle_reader import ParticleReader, ParticleResult, ParticleClass, ParticleFrame
from .plotters import (
    plot_device_timeseries,
    plot_timeseries_interactive,
    plot_hrr,
    plot_slice_contour,
    plot_multi_quantity,
    plot_particle_positions,
)
from .report import SimulationReport, ReportSection
from .comparator import SimulationComparator, ComparisonReport, ChannelComparison
from .batch_analysis import (
    BatchResultAnalyzer, BatchAnalysisReport, VariantSummary, ChannelStats,
)

__all__ = [
    # reader
    "DeviceReader", "LogParser", "SliceReader", "BoundaryReader", "ReaderResult",
    # indexer
    "ResultIndex", "SliceIndex", "BoundaryIndex",
    # plot3d
    "Plot3DReader", "Plot3DResult",
    # particles
    "ParticleReader", "ParticleResult", "ParticleClass", "ParticleFrame",
    # plotters
    "plot_device_timeseries", "plot_timeseries_interactive",
    "plot_hrr", "plot_slice_contour",
    "plot_multi_quantity", "plot_particle_positions",
    # report
    "SimulationReport", "ReportSection",
    # comparator
    "SimulationComparator", "ComparisonReport", "ChannelComparison",
    # batch analysis
    "BatchResultAnalyzer", "BatchAnalysisReport", "VariantSummary", "ChannelStats",
]
