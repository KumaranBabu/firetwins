"""
PyFDS Smokeview Runner
======================
Launch Smokeview (SMV) as a subprocess for interactive visualization or
headless script-driven rendering.

Features
--------
- Interactive launch (blocking or detached)
- Headless rendering via an SSF script file (``-ini`` flag)
- Screenshot / movie capture via SSF + headless mode
- Environment variable fallback for SMV binary path
- EventBus integration: emits ``SMV_LAUNCHED`` and ``SMV_EXITED``

Example::

    from pyfds.smokeview.runner import SmokeviewRunner

    runner = SmokeviewRunner()
    runner.open("case.smv")                          # interactive, blocks

    runner.render("case.smv", script="render.ssf",
                  output_dir="renders/")             # headless, blocks
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

#: Return code of :meth:`SmokeviewRunner.render` when the caller cancelled it.
CANCELLED = -2


class SmokeviewRunner:
    """
    Manages launching the Smokeview binary.

    Parameters
    ----------
    smv_binary : str, optional
        Explicit path to the ``smokeview`` binary. Falls back to the
        ``SMV_BIN`` environment variable, then the string ``"smokeview"``.
    """

    def __init__(self, smv_binary: Optional[str] = None) -> None:
        self._smv_binary = self._resolve_binary(smv_binary or os.getenv("SMV_BIN", "smokeview"))

    @staticmethod
    def _resolve_binary(name: str) -> str:
        """The plain default ``smokeview`` falls back to the repo's bundled build when not on PATH."""
        import shutil
        if name != "smokeview" or shutil.which(name):
            return name
        bundled = Path(__file__).resolve().parents[3] / "fds_smv" / "SMV6" / "smokeview.exe"
        return str(bundled) if bundled.exists() else name

    # ── Public API ────────────────────────────────────────────────────────────

    def open(
        self,
        smv_filepath: str,
        *,
        blocking: bool = True,
        extra_args: Optional[List[str]] = None,
    ) -> Optional[subprocess.Popen]:
        """
        Launch Smokeview for interactive viewing of *smv_filepath*.

        Parameters
        ----------
        smv_filepath : str
            Path to the ``.smv`` metadata file.
        blocking : bool
            If True (default) wait for Smokeview to exit before returning.
        extra_args : list, optional
            Additional command-line arguments appended after the file path.

        Returns
        -------
        subprocess.Popen or None
            The process handle when ``blocking=False``; None otherwise.
        """
        path = Path(smv_filepath)
        if not path.exists():
            raise FileNotFoundError(f"SMV file not found: {smv_filepath}")

        cmd = [self._smv_binary] + (extra_args or []) + [str(path.name)]
        cwd = str(path.parent)

        self._emit_launched(smv_filepath)
        logger.info("SmokeviewRunner: launching %s (blocking=%s)", smv_filepath, blocking)

        try:
            proc = subprocess.Popen(cmd, cwd=cwd)
            if blocking:
                rc = proc.wait()
                self._emit_exited(smv_filepath, rc)
                logger.info("SmokeviewRunner: exited rc=%d", rc)
                return None
            return proc
        except FileNotFoundError:
            logger.error("SmokeviewRunner: binary not found: %s", self._smv_binary)
            raise

    def render(
        self,
        smv_filepath: str,
        *,
        script: Optional[str] = None,
        script_content: Optional[str] = None,
        settings_ini: Optional[str] = None,
        output_dir: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        timeout: Optional[float] = 900.0,
        cancel: Optional[threading.Event] = None,
    ) -> int:
        """
        Run Smokeview with a script (it opens briefly and exits; images land in *output_dir*).

        One of *script* (path to existing ``.ssf``) or *script_content*
        (raw SSF text) must be provided.

        Parameters
        ----------
        smv_filepath : str
            Path to the ``.smv`` metadata file.
        script : str, optional
            Path to an existing SSF script file.
        script_content : str, optional
            SSF commands as a string; written to a temp file if provided.
        settings_ini : str, optional
            Smokeview .ini text loaded before the script runs (``SsfScriptBuilder.settings_ini()``: picture
            size, labels); written to a temp file beside the script.
        output_dir : str, optional
            Working directory for rendered images. Defaults to the smv dir.
        extra_args : list, optional
            Extra arguments before the ``-ini`` flag.
        cancel : threading.Event, optional
            Set it from another thread to stop the render; Smokeview is killed and
            :data:`CANCELLED` is returned.

        Returns
        -------
        int
            Smokeview process return code (0 = success, :data:`CANCELLED` = stopped by *cancel*).
        """
        path = Path(smv_filepath)
        if not path.exists():
            raise FileNotFoundError(f"SMV file not found: {smv_filepath}")

        cwd_path = Path(output_dir) if output_dir else path.parent
        cwd_path.mkdir(parents=True, exist_ok=True)
        cwd = str(cwd_path.resolve())

        # Resolve script path
        tmp_file = None
        tmp_ini = None
        if script_content is not None:
            text = script_content if script_content.rstrip().endswith("EXIT") else script_content.rstrip() + "\nEXIT\n"
            if settings_ini:
                tmp_ini = tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False, dir=cwd)
                tmp_ini.write(settings_ini)
                tmp_ini.close()
                text = f"LOADINIFILE\n {tmp_ini.name}\n" + text
            tmp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".ssf", delete=False, dir=cwd
            )
            tmp_file.write(text)
            tmp_file.flush()
            tmp_file.close()
            script_path = tmp_file.name
        elif script is not None:
            script_path = str(Path(script).resolve())
        else:
            raise ValueError("Either 'script' or 'script_content' must be provided")

        cmd = ([self._smv_binary]
               + (extra_args or [])
               + ["-script", script_path, str(path.resolve())])

        self._emit_launched(smv_filepath)
        logger.info("SmokeviewRunner: scripted render %s  script=%s", smv_filepath, script_path)

        try:
            case_dir = path.resolve().parent
            before = {f: f.stat().st_mtime for f in case_dir.glob("*.[pj][np]g")}
            rc, stderr = self._run_cancellable(cmd, cwd, timeout, cancel)
            # Smokeview writes its images next to the .smv file whatever the working directory is,
            # so move what this run made into the requested folder.
            if case_dir != cwd_path.resolve():
                for f in case_dir.glob("*.[pj][np]g"):
                    if f not in before or f.stat().st_mtime > before[f]:
                        shutil.move(str(f), str(cwd_path / f.name))     # os.replace cannot cross drives
            if rc != 0:
                logger.error("SmokeviewRunner: render failed rc=%d\n%s", rc, stderr)
            else:
                logger.info("SmokeviewRunner: render complete rc=0")
            self._emit_exited(smv_filepath, rc)
            return rc
        except FileNotFoundError:
            logger.error("SmokeviewRunner: binary not found: %s", self._smv_binary)
            raise
        finally:
            for tmp in (tmp_file, tmp_ini):
                if tmp is not None:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass

    @staticmethod
    def _run_cancellable(cmd, cwd, timeout, cancel):
        """Run *cmd* to completion, killing it when *cancel* is set or *timeout* passes."""
        import time
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        start = time.monotonic()
        while True:
            try:
                _, err = proc.communicate(timeout=0.2)
                return proc.returncode, err or ""
            except subprocess.TimeoutExpired:
                pass
            if cancel is not None and cancel.is_set():
                proc.kill()
                proc.communicate()
                return CANCELLED, ""
            if timeout is not None and time.monotonic() - start > timeout:
                proc.kill()
                proc.communicate()
                raise subprocess.TimeoutExpired(cmd, timeout)

    @staticmethod
    def encode_frames(frame_glob_dir: str, base: str, output_file: str, fps: int = 10) -> int:
        """Join ``<base>_0000.png ...`` into a movie with ffmpeg. Returns 0 on success, 127 when ffmpeg is
        not installed (the frames are left where they are)."""
        import shutil
        ff = shutil.which("ffmpeg")
        if ff is None:
            return 127
        r = subprocess.run([ff, "-y", "-framerate", str(fps), "-i", f"{base}_%04d.png", "-pix_fmt", "yuv420p",
                            str(Path(output_file).resolve())], cwd=frame_glob_dir, capture_output=True, text=True)
        return r.returncode

    def capture_screenshots(
        self,
        smv_filepath: str,
        times: List[float],
        quantity: str = "TEMPERATURE",
        output_dir: Optional[str] = None,
        image_format: str = "png",
        axis: int = 2,
        position: float = 0.0,
        cell_centered: bool = False,
    ) -> List[str]:
        """
        High-level helper: render screenshots at given simulation times.

        Generates an SSF script, runs headless Smokeview, and returns
        a list of expected output file paths.

        Parameters
        ----------
        smv_filepath : str
            Path to the ``.smv`` file.
        times : list[float]
            Simulation times at which to capture.
        quantity : str
            Slice or boundary quantity to visualize.
        output_dir : str, optional
            Where to save screenshots. Defaults to SMV file directory.
        image_format : str
            ``"png"`` or ``"jpg"``.

        Returns
        -------
        list[str]
            Expected file paths for each captured image.
        """
        from pyfds.smokeview.scripting import SsfScriptBuilder

        smv_path = Path(smv_filepath)
        out_dir  = Path(output_dir) if output_dir else smv_path.parent

        builder = SsfScriptBuilder()
        builder.load_slice(quantity, axis=axis, position=position, cell_centered=cell_centered)
        out_paths: List[str] = []

        for i, t in enumerate(times):
            stem = f"screenshot_{i:04d}_t{t:.1f}".replace(".", "p")
            builder.set_time(t)
            builder.screenshot(stem)
            out_paths.append(str(out_dir / f"{stem}.{image_format}"))

        self.render(smv_filepath, script_content=builder.build(), settings_ini=builder.settings_ini(),
                    output_dir=str(out_dir))
        return out_paths

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit_launched(self, filepath: str) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(EventType.SMV_LAUNCHED, {"filepath": filepath},
                                  source="SmokeviewRunner")
        except Exception:
            pass

    def _emit_exited(self, filepath: str, rc: int) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(EventType.SMV_EXITED,
                                  {"filepath": filepath, "returncode": rc},
                                  source="SmokeviewRunner")
        except Exception:
            pass
