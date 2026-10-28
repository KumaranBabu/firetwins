"""
PyFDS Simulation Runner
========================
Launches the FDS binary as a subprocess with:
  BUG-04 fix: cwd is the directory containing the .fds input file.
  BUG-05 fix: -e flag (unsupported by FDS) removed entirely.

Live streaming:
  Live stdout/stderr streaming via a reader thread.
  Progress callbacks with step count and simulated time.
  Proper process handle stored so callers can cancel/kill.

LiveMonitor:
  Polls the FDS ``_devc.csv`` and ``.out`` file during a running simulation
  and emits ``HRR_UPDATED`` / ``DEVICE_UPDATED`` events so external consumers
  can react without reading the full CSV on each tick.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from .runner_monitor import (  # noqa: F401  (re-exported)
    LiveMonitor,
    _HRR_RE,
    _TIMED_RE,
    _is_numeric,
)



logger = logging.getLogger(__name__)


# Pattern that matches FDS's step output:  "Step: 123  T: 12.34  ..."
_STEP_RE = re.compile(r'Step:\s*(\d+)\s+T:\s*([\d.]+)', re.IGNORECASE)


class SimulationRunner:
    """
    Manages the lifecycle of a single FDS simulation process.

    Usage::

        runner = SimulationRunner()
        runner.run(
            input_file="/path/to/case.fds",
            num_processes=4,
            on_line=lambda line: print(line),
            on_progress=lambda step, t, pct: print(f"step={step} t={t}"),
            on_complete=lambda success: print("Done:", success),
        )

    Thread safety:
        ``run()`` starts a daemon thread. ``cancel()`` is safe to call from
        any thread and will SIGTERM the FDS process.
    """

    def __init__(self, fds_binary: Optional[str] = None,
                 mpiexec_binary: Optional[str] = None) -> None:
        self._fds_binary = fds_binary or os.getenv("FDS_BIN", "fds")
        self._mpiexec_binary = mpiexec_binary or os.getenv("MPIEXEC_BIN", "mpiexec")
        self._process: Optional[subprocess.Popen] = None
        self.fds_error: Optional[str] = None      # first ERROR line FDS printed in the last run
        self._thread: Optional[threading.Thread] = None
        self._cancel_event = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        input_file: str,
        num_processes: int = 1,
        *,
        on_line: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, float, float], None]] = None,
        on_complete: Optional[Callable[[bool, int], None]] = None,
        timeout: Optional[float] = None,
        env_overrides: Optional[dict] = None,
        command: Optional[List[str]] = None,
    ) -> None:
        """
        Launch FDS in a background daemon thread.

        Parameters
        ----------
        input_file:
            Absolute or relative path to the .fds file.
        num_processes:
            Number of MPI processes (1 = no MPI wrapper).
        on_line:
            Callback receiving each stdout line as a string.
        on_progress:
            Callback ``(step, sim_time, pct)`` where ``pct`` is approximate
            0–100 progress based on T_END read from the .out file.
        on_complete:
            Callback ``(success: bool, returncode: int)`` fired when FDS exits.
        timeout:
            Wall-clock seconds before the process is killed.
        env_overrides:
            Extra environment variables merged into the subprocess environment.
        command:
            A complete command line to run instead of the one built from *num_processes*
            (cluster launches pass their own ``mpiexec -machinefile ...``).
        """
        self._cancel_event.clear()
        abs_input = os.path.abspath(input_file)
        self._input_path = abs_input
        work_dir = os.path.dirname(abs_input)   # BUG-04 fix

        cmd = list(command) if command else self._build_command(abs_input, num_processes)
        env = {**os.environ, **(env_overrides or {})}
        # A Windows FDS install keeps its DLLs (and Intel MPI) next to the binary; without them on PATH the
        # process dies at start-up (exit code 0xC0000135) before FDS can print anything.
        fds_dir = os.path.dirname(os.path.abspath(self._fds_binary)) if os.path.isabs(self._fds_binary) or os.sep in self._fds_binary else ""
        if fds_dir and os.path.isdir(fds_dir):
            extra = [fds_dir] + ([os.path.join(fds_dir, "mpi")] if os.path.isdir(os.path.join(fds_dir, "mpi")) else [])
            env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])

        self._thread = threading.Thread(
            target=self._run_process,
            args=(cmd, work_dir, env, on_line, on_progress, on_complete, timeout),
            daemon=True,
            name=f"pyfds-runner-{Path(abs_input).stem}",
        )
        self._thread.start()
        logger.info("SimulationRunner: launched %s (mpi=%d)", abs_input, num_processes)

    def run_blocking(
        self,
        input_file: str,
        num_processes: int = 1,
        **kwargs,
    ) -> int:
        """
        Run FDS and block until it finishes.

        Returns
        -------
        int
            Process return code (0 = success).
        """
        result_box = [None]

        def _on_complete(success: bool, rc: int) -> None:
            # FDS exits with 0 after rejecting its input; report that as a failure code
            result_box[0] = -2 if (rc == 0 and not success and self.fds_error) else rc

        self.run(input_file, num_processes, on_complete=_on_complete, **kwargs)
        self.wait()
        return result_box[0] if result_box[0] is not None else -1

    def cancel(self) -> None:
        """Request cancellation. The FDS process receives SIGTERM."""
        self._cancel_event.set()
        if self._process and self._process.poll() is None:
            try:
                if not self._kill_tree():
                    self._process.terminate()
                logger.info("SimulationRunner: sent SIGTERM to FDS process")
            except OSError:
                pass

    def kill(self) -> None:
        """Forcibly kill the FDS process with SIGKILL."""
        self._cancel_event.set()
        if self._process and self._process.poll() is None:
            try:
                if not self._kill_tree():
                    self._process.kill()
                logger.warning("SimulationRunner: sent SIGKILL to FDS process")
            except OSError:
                pass

    def _kill_tree(self) -> bool:
        """On Windows end the launcher, its FDS ranks and the hydra proxy that started them. The proxy is not a child of
        mpiexec, so ending mpiexec alone leaves the ranks running and holding the output pipe open (the runner would
        never return). The ranks are found by their command line (this run's input file), then their proxies. Returns
        False where the plain process call should be used."""
        if os.name != "nt" or self._process is None:
            return False
        try:
            marker = getattr(self, "_input_path", "").replace("'", "''")
            if marker:
                script = ("$r = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'fds*.exe' -and "
                          f"$_.CommandLine -like '*{marker}*' }}; "
                          "$p = $r | ForEach-Object { $_.ParentProcessId } | Sort-Object -Unique; "
                          "foreach ($i in $p) { $q = Get-Process -Id $i -ErrorAction SilentlyContinue; "
                          "if ($q -and $q.ProcessName -like 'hydra*') { Stop-Process -Id $i -Force } }; "
                          "$r | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
                subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=30)
            subprocess.run(["taskkill", "/PID", str(self._process.pid), "/T", "/F"], capture_output=True, timeout=15)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until the runner thread exits. Returns True if it finished."""
        if self._thread:
            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()
        return True

    @property
    def is_running(self) -> bool:
        return bool(self._process and self._process.poll() is None)

    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process else None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_command(self, abs_input: str, num_processes: int) -> List[str]:
        fds_bin = self._fds_binary
        is_bat = fds_bin.lower().endswith((".bat", ".cmd"))

        if num_processes > 1:
            if is_bat:
                # Windows batch launcher that wraps MPI
                return [fds_bin, "-p", str(num_processes), abs_input]
            else:
                return [self._mpiexec_binary, "-n", str(num_processes),
                        fds_bin, abs_input]
        else:
            return [fds_bin, abs_input]
        # NOTE: No -e flag (BUG-05 fix) — t_end must be written into the .fds file.

    def _run_process(
        self,
        cmd: List[str],
        work_dir: str,
        env: dict,
        on_line,
        on_progress,
        on_complete,
        timeout: Optional[float],
    ) -> None:
        """Target for the runner thread."""
        from pyfds.core.events import get_global_bus, EventType
        bus = get_global_bus()

        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=work_dir,               # BUG-04 fix: input file directory
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,   # merge stderr into stdout stream
                text=True,
                bufsize=1,
            )
            bus.emit(EventType.JOB_STARTED, {"pid": self._process.pid},
                     source="SimulationRunner")

            deadline = time.monotonic() + timeout if timeout else None
            fds_error: Optional[str] = None     # FDS exits with code 0 even when it rejects the input file
            self.fds_error = None

            # Stream output line by line
            for raw_line in self._process.stdout:
                if self._cancel_event.is_set():
                    break

                line = raw_line.rstrip()
                if fds_error is None and line.startswith("ERROR"):
                    fds_error = line
                bus.emit(EventType.JOB_OUTPUT_LINE, line, source="SimulationRunner")

                if on_line:
                    try:
                        on_line(line)
                    except Exception:
                        pass

                if on_progress:
                    self._parse_progress(line, on_progress, bus)

                if deadline and time.monotonic() > deadline:
                    logger.warning("SimulationRunner: timeout reached, killing process")
                    self.kill()
                    break

            self._process.wait()
            rc = self._process.returncode
            success = (rc == 0) and not self._cancel_event.is_set() and fds_error is None
            if fds_error:
                self.fds_error = fds_error
                logger.error("SimulationRunner: FDS reported: %s", fds_error)

            bus.emit(EventType.JOB_COMPLETED if success else EventType.JOB_FAILED,
                     {"returncode": rc, "success": success},
                     source="SimulationRunner")

            if on_complete:
                try:
                    on_complete(success, rc)
                except Exception:
                    pass

            if not success and not self._cancel_event.is_set():
                logger.error("SimulationRunner: FDS exited with code %d", rc)
            else:
                logger.info("SimulationRunner: FDS completed (rc=%d)", rc)

        except FileNotFoundError:
            msg = f"FDS binary not found: {cmd[0]!r}"
            logger.error(msg)
            bus.emit(EventType.JOB_FAILED, {"error": msg}, source="SimulationRunner")
            if on_complete:
                on_complete(False, -1)
        except Exception as exc:
            logger.error("SimulationRunner unexpected error: %s", exc, exc_info=True)
            if on_complete:
                on_complete(False, -1)

    def _parse_progress(self, line: str, on_progress, bus) -> None:
        from pyfds.core.events import EventType
        m = _STEP_RE.search(line)
        if m:
            step = int(m.group(1))
            sim_t = float(m.group(2))
            try:
                on_progress(step, sim_t, 0.0)
            except Exception:
                pass
            bus.emit(EventType.JOB_PROGRESS,
                     {"step": step, "time": sim_t},
                     source="SimulationRunner")
