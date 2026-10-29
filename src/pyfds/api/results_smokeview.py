"""SmokeviewManager: Smokeview scripts, screenshots, movies, ini files."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from .facade import FdsApi


class SmokeviewManager:
    """
    Launch Smokeview, drive headless rendering, write INI scene config,
    and generate SSF scripts.

    Accessible via ``api.smokeview``.
    """

    def run_script(self, smv_path: str, script_content: str, output_dir: Optional[str] = None,
                   settings_ini: Optional[str] = None) -> int:
        """Run Smokeview headless on *smv_path* with the given SSF script text (and the builder's
        ``settings_ini()``: picture size, labels); returns its exit code."""
        from pyfds.smokeview.runner import SmokeviewRunner
        return SmokeviewRunner().render(smv_path, script_content=script_content, settings_ini=settings_ini,
                                        output_dir=output_dir)

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
        """(axis 1/2/3, position, cell-centred) of a slice to show: the project's own slice of that quantity,
        else the middle of the first mesh on the y plane."""
        p = self._api.project
        for sl in p.slices:
            if sl.quantity == quantity and getattr(sl, "plane", None) in ("X", "Y", "Z"):
                return "XYZ".index(sl.plane) + 1, float(sl.position), bool(getattr(sl, "cell_centered", False))
        m = p.meshes[0] if p.meshes else None
        return 2, ((m.y_min + m.y_max) / 2 if m else 0.0), False

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
        axis, pos, cell = self._slice_plane(quantity)
        return SmokeviewRunner(
            smv_binary=getattr(cfg, "smv_binary", None)
        ).capture_screenshots(smv_filepath, times, quantity=quantity,
                               output_dir=output_dir, axis=axis, position=pos, cell_centered=cell)

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
        cancel: Any = None,
    ) -> int:
        """
        Render every frame of *quantity* with Smokeview and join them into *output_file* with ffmpeg.

        Setting the *cancel* ``threading.Event`` stops the render (returns ``runner.CANCELLED``).

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
        axis, pos, cell = self._slice_plane(quantity)
        builder = SsfScriptBuilder()
        builder.load_slice(quantity=quantity, axis=axis, position=pos, cell_centered=cell)
        if start_time is not None:
            builder.set_time(start_time)
        builder.render_movie(out.stem)
        runner = SmokeviewRunner(smv_binary=getattr(cfg, "smv_binary", None))
        rc = runner.render(smv_filepath, script_content=builder.build(), settings_ini=builder.settings_ini(),
                           output_dir=str(frames_dir), cancel=cancel)
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
