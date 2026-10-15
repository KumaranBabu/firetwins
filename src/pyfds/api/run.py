"""Running FDS: execution, batch studies, HPC jobs.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class ExecutionManager:
    """Submit and track FDS simulation jobs."""

    def __init__(self, api: "FdsApi") -> None:
        self._api   = api
        self._queue = None

    def _ensure_queue(self):
        if self._queue is None:
            from pyfds.execution.queue import JobQueue
            cfg = self._api.config
            self._queue = JobQueue(
                max_workers=getattr(cfg, "max_workers", 2),
                fds_binary=getattr(cfg, "fds_binary", None),
            )
            self._queue.start()
        return self._queue

    def run_async(
        self,
        output_dir: Optional[str] = None,
        *,
        open_smokeview: bool = False,
        validate_first: bool = True,
        num_processes: int = 1,
        timeout: Optional[float] = None,
    ) -> Any:
        """Submit the run pipeline on a background thread; returns a ``concurrent.futures.Future``."""
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self.run,
            output_dir,
            open_smokeview=open_smokeview,
            validate_first=validate_first,
            num_processes=num_processes,
            timeout=timeout,
        )
        executor.shutdown(wait=False)
        return future

    def run(
        self,
        output_dir: Optional[str] = None,
        *,
        open_smokeview: bool = False,
        validate_first: bool = True,
        num_processes: int = 1,
        timeout: Optional[float] = None,
        fds_binary: Optional[str] = None,
    ) -> Any:
        """
        Full pipeline: validate → write → run → collect results.

        Returns an ``OrchestratorResult``.
        """
        from pyfds.automation.orchestrator import ScenarioOrchestrator
        cfg     = self._api.config
        out_dir = output_dir or getattr(cfg, "output_dir", "output")
        orch = ScenarioOrchestrator(
            output_dir=out_dir,
            run_simulations=True,
            open_smokeview=open_smokeview,
            fds_binary=fds_binary or getattr(cfg, "fds_binary", None),
            smv_binary=getattr(cfg, "smv_binary", None),
            max_processes=num_processes,
            timeout=timeout,
            validate_before_run=validate_first,
        )
        return orch.run(self._api.project)

    def submit_job(self, fds_filepath: str, output_dir: str, **kwargs) -> Any:
        from pyfds.execution.job import Job
        job = Job(fds_filepath=fds_filepath, output_directory=output_dir, **kwargs)
        self._ensure_queue().submit(job)
        return job

    def cancel_job(self, job_id: str) -> bool:
        q = self._ensure_queue()
        return q.cancel(job_id)

    def cancel_all(self) -> None:
        self._ensure_queue().cancel_all()

    def all_jobs(self) -> List[Any]:
        return self._ensure_queue().all_jobs() if self._queue else []

    def wait_all(self) -> None:
        if self._queue:
            self._queue.wait_all()

    def shutdown(self) -> None:
        if self._queue:
            self._queue.stop(wait=True)
            self._queue = None

    def live_monitor(
        self,
        output_dir: str,
        chid: Optional[str] = None,
        *,
        poll_interval: float = 2.0,
        on_hrr=None,
        on_devices=None,
    ) -> Any:
        """
        Create and start a ``LiveMonitor`` that polls FDS output files.

        Parameters
        ----------
        output_dir : str
            Directory where FDS writes its output files.
        chid : str, optional
            Case ID stem (``<chid>_devc.csv``, ``<chid>_hrr.csv``).
            Defaults to the current project's CHID.
        poll_interval : float
            Seconds between file reads.
        on_hrr : callable, optional
            ``(time, hrr_kW)`` callback.
        on_devices : callable, optional
            ``(time, {name: value})`` callback.

        Returns
        -------
        LiveMonitor
            Already started — call ``.stop()`` when done.
        """
        from pyfds.execution.runner import LiveMonitor
        _chid = chid or getattr(self._api.project, "chid", "case")
        monitor = LiveMonitor(
            output_dir, _chid,
            poll_interval=poll_interval,
            on_hrr=on_hrr,
            on_devices=on_devices,
        )
        monitor.start()
        return monitor

    def run_batch(
        self,
        study: Any,
        output_root: Optional[str] = None,
        max_workers: int = 2,
        run_simulations: bool = True,
    ) -> Any:
        """Convenience shortcut — runs a ParametricStudy through BatchExecutor."""
        return self._api.batch.run_study(
            study,
            output_root=output_root,
            max_workers=max_workers,
            run_simulations=run_simulations,
        )

    def resume_from_checkpoint(
        self,
        fds_filepath: str,
        *,
        output_dir: Optional[str] = None,
        num_processes: int = 1,
        timeout: Optional[float] = None,
        fds_binary: Optional[str] = None,
    ) -> Any:
        """
        Resume a stopped FDS simulation from its checkpoint (restart) files.

        Parses *fds_filepath*, sets ``MISC RESTART=.TRUE.``, writes a new
        ``<stem>_restart.fds`` alongside the original, and runs it.

        Parameters
        ----------
        fds_filepath : str
            Path to the original FDS input file.
        output_dir : str, optional
            Output directory for the restarted run.
            Defaults to a ``restart_output/`` subdirectory next to the file.
        """
        from pathlib import Path as _Path
        from pyfds.io.fds_parser import FdsParser
        from pyfds.io.fds_writer import FdsWriter
        from pyfds.domain.model import MiscParams

        p = _Path(fds_filepath)
        proj = FdsParser().parse(str(p))
        if proj.misc is None:
            proj.misc = MiscParams()
        proj.misc.restart = True

        restart_path = str(p.parent / f"{p.stem}_restart{p.suffix}")
        FdsWriter().write(proj, restart_path)

        out_dir = output_dir or str(p.parent / "restart_output")
        from pyfds.automation.orchestrator import ScenarioOrchestrator
        cfg = self._api.config
        orch = ScenarioOrchestrator(
            output_dir=out_dir,
            run_simulations=True,
            fds_binary=fds_binary or getattr(cfg, "fds_binary", None),
            smv_binary=getattr(cfg, "smv_binary", None),
            max_processes=num_processes,
            timeout=timeout,
            validate_before_run=False,
        )
        return orch.run(proj)


class BatchManager:
    """Manage parametric / batch simulation studies."""

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    def create_study(self, name: str) -> Any:
        from pyfds.execution.batch import ParametricStudy
        cfg  = self._api.config
        study = ParametricStudy(name=name,
                                base_fds_file=getattr(cfg, "fds_binary", ""))
        return study

    def load_config(self, path: str) -> Any:
        """Read a batch-study JSON file. Raises ``ValueError`` (with a readable message) if it is invalid."""
        from pyfds.execution.batch_config import BatchStudyConfig, BatchConfigError
        try:
            return BatchStudyConfig.from_file(path)
        except BatchConfigError as exc:
            raise ValueError(str(exc)) from exc

    def analyze(self, output_root: str, study_name: Optional[str] = None, outlier_sigma: float = 3.0) -> Any:
        """Statistics over a finished study: a report with ``summary()``, ``to_csv/html/json``."""
        from pyfds.results.batch_analysis import BatchResultAnalyzer
        return BatchResultAnalyzer(output_root, study_name=study_name, outlier_sigma=outlier_sigma).analyze()

    def run_study(
        self,
        study: Any,
        output_root: Optional[str] = None,
        max_workers: int = 2,
        run_simulations: bool = True,
    ) -> Any:
        from pyfds.execution.batch import BatchExecutor
        cfg      = self._api.config
        out_root = output_root or "batch_results"
        executor = BatchExecutor(
            output_root=out_root,
            max_workers=max_workers,
            run_simulations=run_simulations,
            fds_binary=getattr(cfg, "fds_binary", None),
        )
        return executor.run(study)


class HpcJobManager:
    """
    HPC cluster job script generation and submission.

    Accessible via ``api.hpc``.
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    def _manager(self, dry_run: bool = False, script_dir: Optional[str] = None):
        from pyfds.execution.hpc import HpcManager
        return HpcManager(script_dir=script_dir, dry_run=dry_run)

    def submit_slurm(self, fds_input: str, output_dir: str, **kwargs) -> Any:
        """Generate and submit a SLURM job. Returns ``HpcSubmitResult``."""
        return self._manager().submit_slurm(fds_input, output_dir, **kwargs)

    def submit_pbs(self, fds_input: str, output_dir: str, **kwargs) -> Any:
        """Generate and submit a PBS job. Returns ``HpcSubmitResult``."""
        return self._manager().submit_pbs(fds_input, output_dir, **kwargs)

    def submit_lsf(self, fds_input: str, output_dir: str, **kwargs) -> Any:
        """Generate and submit an LSF job. Returns ``HpcSubmitResult``."""
        return self._manager().submit_lsf(fds_input, output_dir, **kwargs)

    def generate_script(
        self, scheduler: str, fds_input: str, output_dir: str, **kwargs
    ) -> str:
        """Return the job script string without submitting."""
        return self._manager(dry_run=True).generate_script(
            scheduler, fds_input, output_dir, **kwargs
        )

    def dry_run(self, scheduler: str, fds_input: str, output_dir: str, **kwargs) -> Any:
        """Write the script file but do not submit. Returns ``HpcSubmitResult``."""
        fn = {
            "slurm": self._manager(dry_run=True).submit_slurm,
            "pbs":   self._manager(dry_run=True).submit_pbs,
            "lsf":   self._manager(dry_run=True).submit_lsf,
        }.get(scheduler.lower())
        if fn is None:
            raise ValueError(f"Unknown scheduler {scheduler!r}. Use 'slurm', 'pbs', or 'lsf'.")
        return fn(fds_input, output_dir, **kwargs)
