"""Results indexing/reading and Smokeview integration.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, TYPE_CHECKING


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

    def read_device(self, device_name: str) -> Optional[Any]:
        if self._index is None:
            return None
        return self._index.read_device(device_name)

    def find_slices(self, quantity: str) -> List[Any]:
        if self._index is None:
            return []
        return self._index.find_slices(quantity=quantity)

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


class SmokeviewManager:
    """
    Launch Smokeview, drive headless rendering, write INI scene config,
    and generate SSF scripts.

    Accessible via ``api.smokeview``.
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    # ── Launch ────────────────────────────────────────────────────────────────

    def open(self, smv_filepath: str, *, blocking: bool = True) -> None:
        """Open Smokeview interactively."""
        from pyfds.smokeview.runner import SmokeviewRunner
        cfg = self._api.config
        SmokeviewRunner(smv_binary=getattr(cfg, "smv_binary", None)).open(
            smv_filepath, blocking=blocking
        )

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _slice_plane(self, quantity: str):
        """(axis 1/2/3, position) of a slice to show: the project's own slice of that quantity, else the middle
        of the first mesh on the y plane."""
        p = self._api.project
        for sl in p.slices:
            if sl.quantity == quantity and getattr(sl, "plane", None) in ("X", "Y", "Z"):
                return "XYZ".index(sl.plane) + 1, float(sl.position)
        m = p.meshes[0] if p.meshes else None
        return 2, ((m.y_min + m.y_max) / 2 if m else 0.0)

    def render_screenshots(
        self,
        smv_filepath: str,
        times: List[float],
        quantity: str = "TEMPERATURE",
        output_dir: Optional[str] = None,
    ) -> List[str]:
        """Render screenshots of a slice at given simulation times (real Smokeview). Returns the image paths."""
        from pyfds.smokeview.runner import SmokeviewRunner
        cfg = self._api.config
        axis, pos = self._slice_plane(quantity)
        return SmokeviewRunner(
            smv_binary=getattr(cfg, "smv_binary", None)
        ).capture_screenshots(smv_filepath, times, quantity=quantity,
                               output_dir=output_dir, axis=axis, position=pos)

    def render_movie(
        self,
        smv_filepath: str,
        output_file: str,
        quantity: str = "TEMPERATURE",
        *,
        fps: int = 10,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        output_dir: Optional[str] = None,
    ) -> int:
        """
        Render every frame of *quantity* with Smokeview and join them into *output_file* with ffmpeg.

        Returns 0 on success; 127 when ffmpeg is not installed (the numbered PNG frames are left next to
        *output_file*); otherwise Smokeview's or ffmpeg's return code. *end_time* is not supported by
        Smokeview's script (it renders to the last frame); *start_time* sets where it begins.
        """
        from pathlib import Path
        from pyfds.smokeview.runner import SmokeviewRunner
        from pyfds.smokeview.scripting import SsfScriptBuilder
        cfg = self._api.config
        out = Path(output_file).resolve()
        frames_dir = Path(output_dir).resolve() if output_dir else out.parent
        axis, pos = self._slice_plane(quantity)
        builder = SsfScriptBuilder()
        builder.load_slice(quantity=quantity, axis=axis, position=pos)
        if start_time is not None:
            builder.set_time(start_time)
        builder.render_movie(out.stem)
        runner = SmokeviewRunner(smv_binary=getattr(cfg, "smv_binary", None))
        rc = runner.render(smv_filepath, script_content=builder.build(), output_dir=str(frames_dir))
        if rc != 0:
            return rc
        return runner.encode_frames(str(frames_dir), out.stem, str(out), fps)

    # ── Scripting ─────────────────────────────────────────────────────────────

    def build_script(self) -> Any:
        """Return a blank :class:`SsfScriptBuilder`."""
        from pyfds.smokeview.scripting import SsfScriptBuilder
        return SsfScriptBuilder()

    def script_from_metadata(
        self,
        smv_filepath: str,
        *,
        quantity: str = "TEMPERATURE",
        times: Optional[List[float]] = None,
    ) -> Any:
        """
        Auto-generate an SSF script from a parsed ``.smv`` file.

        Loads the first available slice matching *quantity* and either
        steps through all *times* or renders a single frame at the end.

        Returns a populated :class:`SsfScriptBuilder`.
        """
        from pyfds.smokeview.smv_parser import SmvParser
        from pyfds.smokeview.scripting import SsfScriptBuilder

        meta = SmvParser().parse(smv_filepath)
        builder = SsfScriptBuilder()
        builder.set_render_options(width=1280, height=720)

        # Find matching slice
        matching = [s for s in meta.slices if s.quantity == quantity]
        if matching:
            builder.load_slice(quantity=quantity, mesh=matching[0].mesh_id)
        elif meta.slices:
            builder.load_slice(quantity=meta.slices[0].quantity,
                               mesh=meta.slices[0].mesh_id)

        # Set viewpoint if any defined
        if meta.viewpoints:
            builder.set_viewpoint(meta.viewpoints[0].name)

        if times:
            for t in times:
                builder.set_time(t)
                builder.screenshot()
        else:
            builder.screenshot()

        return builder

    # ── INI file ──────────────────────────────────────────────────────────────

    def build_ini_config(self) -> Any:
        """Return a blank :class:`SmvIniConfig` for scene configuration."""
        from pyfds.smokeview.ini_writer import SmvIniConfig
        return SmvIniConfig()

    def write_ini(self, config: Any, filepath: str) -> None:
        """Write a :class:`SmvIniConfig` to *filepath* as a ``.ini`` file."""
        from pyfds.smokeview.ini_writer import SmvIniWriter
        SmvIniWriter().write(config, filepath)

    def ini_from_project(self, output_filepath: Optional[str] = None) -> Any:
        """
        Auto-generate a :class:`SmvIniConfig` from the active FDS project.

        Reads surface names and colors from the project and creates matching
        INI colorbar / surface-color entries.  Returns the config object and
        optionally writes it to *output_filepath*.
        """
        from pyfds.smokeview.ini_writer import SmvIniConfig, SmvIniWriter
        project = self._api.project
        cfg = SmvIniConfig()

        # Map FDS surface colors → SMV surface display colors
        for surf in getattr(project, "surfaces", []):
            if hasattr(surf, "rgb") and surf.rgb:
                cfg.add_surface_color(surf.name, rgb=surf.rgb)

        if output_filepath:
            SmvIniWriter().write(cfg, output_filepath)
        return cfg

    # ── Parsing ───────────────────────────────────────────────────────────────

    def parse_smv(self, smv_filepath: str) -> Any:
        """Parse an ``.smv`` file and return :class:`SmvMetadata`."""
        from pyfds.smokeview.smv_parser import SmvParser
        return SmvParser().parse(smv_filepath)

    def parse_ini(self, ini_filepath: str) -> Any:
        """Parse a ``.ini`` scene-config file and return :class:`SmvIniConfig`."""
        from pyfds.smokeview.ini_writer import SmvIniParser
        return SmvIniParser().parse(ini_filepath)
