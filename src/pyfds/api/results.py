"""Results indexing/reading and Smokeview integration.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, TYPE_CHECKING

from .results_smokeview import (  # noqa: F401  (re-exported)
    SmokeviewManager,
)



if TYPE_CHECKING:
    from .facade import FdsApi


logger = logging.getLogger(__name__)


class ResultsManager:
    """Index and query post-simulation result files."""

    def __init__(self, api: "FdsApi") -> None:
        self._api = api
        self._index: Optional[Any] = None

    def build_index(self, output_dir: Optional[str] = None, *, use_smv: bool = True) -> Any:
        from pyfds.results.indexer import ResultIndex
        chid    = getattr(self._api.project, "chid", "pyfds_case")
        out_dir = output_dir or "output"
        self._index = ResultIndex.build(out_dir, chid=chid, use_smv=use_smv)
        return self._index

    def build_index_from_smv(self, smv_filepath: str) -> Any:
        """Build the result index directly from a ``.smv`` file (fastest path)."""
        from pyfds.results.indexer import ResultIndex
        self._index = ResultIndex.build_from_smv(smv_filepath)
        return self._index

    @property
    def index(self) -> Optional[Any]:
        return self._index

    # -- reading single result files (used by the command line and scripts) -------------
    @staticmethod
    def device_data(csv_path: str) -> Any:
        from pyfds.results.reader import DeviceReader
        return DeviceReader().read(csv_path)

    @staticmethod
    def smv_metadata(smv_path: str) -> Any:
        from pyfds.smokeview.smv_parser import SmvParser
        return SmvParser().parse(smv_path)

    @staticmethod
    def plot3d(q_path: str) -> Any:
        from pyfds.results.plot3d_reader import Plot3DReader
        return Plot3DReader.read(q_path)

    @staticmethod
    def particles(prt5_path: str) -> Any:
        from pyfds.results.particle_reader import ParticleReader
        return ParticleReader.read(prt5_path)

    @staticmethod
    def summary(output_dir: str) -> str:
        """Text summary of what a results folder holds."""
        from pyfds.results.indexer import ResultIndex
        return ResultIndex.build(str(output_dir)).summary()

    @staticmethod
    def build_report(output_dir: str, title: Optional[str] = None) -> Any:
        """A ``SimulationReport`` for a results folder; it also carries ``chid`` for naming the file."""
        from pyfds.results.indexer import ResultIndex
        from pyfds.results.report import SimulationReport
        idx = ResultIndex.build(str(output_dir))
        report = SimulationReport(stats=idx.stats, title=title or f"Simulation Report - {idx.chid}")
        report.chid = idx.chid
        return report

    def device_figure(self, device_name: str, only_this: bool = False, index: Any = None) -> Any:
        """A time-series figure (matplotlib) from the file holding the named device of the current results
        index: every channel in that file, or just *device_name* with ``only_this``."""
        index = index if index is not None else self._index
        if index is None:
            raise RuntimeError("build the results index first (api.results.build_index)")
        from pyfds.results.reader import DeviceReader
        from pyfds.results.plotters import plot_device_timeseries
        path = index.find_device_file(device_name)
        if path is None:
            raise KeyError(f"no device data for {device_name!r}")
        data = DeviceReader.read(path)
        return plot_device_timeseries(data, device_names=[device_name]) if only_this else plot_device_timeseries(data)

    def read_device(self, device_name: str) -> Optional[Any]:
        if self._index is None:
            return None
        return self._index.read_device(device_name)

    def find_slices(self, quantity: str) -> List[Any]:
        if self._index is None:
            return []
        return self._index.find_slices(quantity=quantity)

    def _dir_chid(self, output_dir: Optional[str], chid: Optional[str]):
        if output_dir is None and self._index is not None:
            output_dir = self._index.output_dir
        if not output_dir:
            raise ValueError("give output_dir (or build the results index first)")
        return output_dir, chid or (self._index.chid if self._index is not None and self._index.chid else None)             or getattr(self._api.project, "chid", "pyfds_case")

    def activation_table(self, output_dir: Optional[str] = None, chid: Optional[str] = None) -> List[dict]:
        """When each device and control first activated, earliest first (TH-03):
        ``[{"id", "type" (DEVC|CTRL), "time", "value", "units"}]``."""
        from pyfds.results.summary import activation_table
        return activation_table(*self._dir_chid(output_dir, chid))

    def hrr_summary(self, output_dir: Optional[str] = None, chid: Optional[str] = None,
                    thresholds_kw: Optional[List[float]] = None) -> dict:
        """Peak HRR and its time, total energy (MJ), average HRR and time to reach thresholds (TH-03)."""
        from pyfds.results.summary import hrr_summary
        d, c = self._dir_chid(output_dir, chid)
        return hrr_summary(d, c, thresholds_kw)

    def simulation_stats(self) -> Optional[Any]:
        return self._index.stats if self._index else None

    def read_plot3d(self, path: Optional[str] = None) -> Optional[Any]:
        """
        Read a Plot3D ``*.q`` file and return a ``Plot3DResult``.

        If *path* is None the first file discovered by ``build_index()`` is used.
        Returns None if no file is available.
        """
        from pyfds.results.plot3d_reader import Plot3DReader
        if path is None:
            if self._index is None or not self._index.plot3d_files:
                return None
            path = self._index.plot3d_files[0]
        return Plot3DReader.read(path)

    def read_particles(self, path: Optional[str] = None) -> Optional[Any]:
        """
        Read a particle ``*.prt5`` file and return a ``ParticleResult``.

        If *path* is None the first file discovered by ``build_index()`` is used.
        Returns None if no file is available.
        """
        from pyfds.results.particle_reader import ParticleReader
        if path is None:
            if self._index is None or not self._index.particle_files:
                return None
            path = self._index.particle_files[0]
        return ParticleReader.read(path)

    def plot(self, result: Any, kind: str = "auto", **kwargs) -> Any:
        """
        Plot any Phase-2 result object, returning a ``matplotlib.figure.Figure``.

        Parameters
        ----------
        result
            A dict (device results), ``Plot3DResult``, ``ParticleClass``,
            or slice ``ReaderResult``.
        kind : str
            ``"auto"`` infers from *result* type.  Explicit choices:
            ``"device_timeseries"``, ``"hrr"``, ``"slice_contour"``,
            ``"multi_quantity"``, ``"particle_positions"``.
        **kwargs
            Forwarded to the underlying plotter function.
        """
        from pyfds.results import plotters
        if kind == "auto":
            kind = self._infer_plot_kind(result)
        dispatch = {
            "device_timeseries":      plotters.plot_device_timeseries,
            "interactive_timeseries": plotters.plot_timeseries_interactive,
            "hrr":                    plotters.plot_hrr,
            "slice_contour":          plotters.plot_slice_contour,
            "multi_quantity":         plotters.plot_multi_quantity,
            "particle_positions":     plotters.plot_particle_positions,
        }
        fn = dispatch.get(kind)
        if fn is None:
            raise ValueError(
                f"Unknown plot kind {kind!r}. Choose from: {list(dispatch)}"
            )
        return fn(result, **kwargs)

    def _infer_plot_kind(self, result: Any) -> str:
        if isinstance(result, dict):
            return "device_timeseries"
        type_name = type(result).__name__
        if type_name == "Plot3DResult":
            return "multi_quantity"
        if type_name == "ParticleClass":
            return "particle_positions"
        return "slice_contour"

    def animate(self, result: Any, kind: str = "auto", **kwargs) -> Any:
        """
        Build an animation from a result object.

        Parameters
        ----------
        result
            A slice ``ReaderResult`` or ``ParticleClass``.
        kind : str
            ``"auto"`` infers from type.  Explicit: ``"slice"`` or ``"particles"``.
        **kwargs
            Forwarded to :func:`~pyfds.results.plotters.animate_slice` or
            :func:`~pyfds.results.plotters.animate_particles`.

        Returns
        -------
        matplotlib.animation.FuncAnimation
        """
        from pyfds.results import plotters
        if kind == "auto":
            type_name = type(result).__name__
            kind = "particles" if type_name == "ParticleClass" else "slice"
        if kind == "slice":
            return plotters.animate_slice(result, **kwargs)
        elif kind == "particles":
            return plotters.animate_particles(result, **kwargs)
        else:
            raise ValueError(f"Unknown animation kind {kind!r}. Use 'slice' or 'particles'.")

    def compare(
        self,
        baseline_dir: str,
        variant_dir: str,
        threshold_pct: float = 5.0,
    ) -> Any:
        """
        Compare two result directories channel-by-channel.

        Returns a :class:`~pyfds.results.comparator.ComparisonReport`.
        """
        from pyfds.results.comparator import SimulationComparator
        cmp = SimulationComparator(baseline_dir, variant_dir)
        return cmp.compare(threshold_pct=threshold_pct)

    def analyze_batch(
        self,
        output_root: str,
        study_name: Optional[str] = None,
        *,
        outlier_sigma: float = 2.0,
    ) -> Any:
        """
        Post-process a completed parametric study.

        Discovers variant subdirectories under *output_root* / *study_name*,
        reads device CSV from each run, computes cross-variant statistics, and
        returns a :class:`~pyfds.results.batch_analysis.BatchAnalysisReport`.
        """
        from pyfds.results.batch_analysis import BatchResultAnalyzer
        analyzer = BatchResultAnalyzer(
            output_root, study_name=study_name, outlier_sigma=outlier_sigma
        )
        return analyzer.analyze()

    def archive(self, filepath: str) -> None:
        """
        Serialise the current result index to a JSON file.

        Raises ``RuntimeError`` if no index has been built yet.
        """
        if self._index is None:
            raise RuntimeError("No index built. Call build_index() first.")
        self._index.save(filepath)

    def restore(self, filepath: str) -> Any:
        """
        Load a previously archived result index from *filepath*.

        Returns the restored :class:`~pyfds.results.indexer.ResultIndex`.
        """
        from pyfds.results.indexer import ResultIndex
        self._index = ResultIndex.load(filepath)
        return self._index

    def generate_report(
        self,
        title: str = "FDS Simulation Report",
        *,
        device_results: Optional[Any] = None,
        validation_report: Optional[Any] = None,
    ) -> Any:
        """
        Build a ``SimulationReport`` from the current index state.

        Parameters
        ----------
        title : str
            Report heading.
        device_results : dict, optional
            ``DeviceReader.read()`` output to include a device summary section.
        validation_report : object, optional
            Object with ``.issues`` iterable (e.g. from the validation engine).
        """
        from pyfds.results.report import SimulationReport
        stats = self._index.stats if self._index else None
        return SimulationReport(
            stats=stats,
            title=title,
            device_results=device_results,
            validation_report=validation_report,
        )
