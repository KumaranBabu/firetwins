"""
PyFDS Scenario Orchestrator
============================
High-level controller that chains together the full simulation pipeline:
validate → write .fds → run FDS → collect results → (optional) render.

BUG-09 fix
~~~~~~~~~~
The original ``orchestrator.py`` called ``self._runner.run(project)`` on
``SimulationRunner`` — but ``SimulationRunner.run()`` expects a *filepath*,
not a project object.  The original orchestrator also never wrote the .fds
file before running, so FDS always failed.

This rewrite:
  1. Validates the project via ``ValidationEngine``.
  2. Writes the .fds file via ``FdsWriter``.
  3. Runs FDS via ``SimulationRunner.run_blocking(filepath)``.
  4. Collects results via ``ResultIndex``.
  5. Optionally launches Smokeview.

Example::

    from pyfds.automation.orchestrator import ScenarioOrchestrator

    orch = ScenarioOrchestrator(
        output_dir="runs/corridor_smoke",
        run_simulations=True,
        open_smokeview=False,
    )
    result = orch.run(project)
    print(result.success, result.stats.t_reached)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Summary of an orchestrated simulation run."""
    success: bool = False
    fds_filepath: str = ""
    output_dir: str = ""
    validation_passed: bool = False
    validation_summary: str = ""
    return_code: int = -1
    wall_time_seconds: float = 0.0
    stats: object = None           # SimulationStats from LogParser
    error: str = ""

    def __repr__(self) -> str:
        return (f"<OrchestratorResult success={self.success} "
                f"rc={self.return_code} wall={self.wall_time_seconds:.1f}s>")


class ScenarioOrchestrator:
    """
    Orchestrates the complete single-scenario pipeline.

    Parameters
    ----------
    output_dir : str
        Directory in which the ``.fds`` file is written and FDS output
        files are placed.
    run_simulations : bool
        Set False to only write and validate without running FDS.
    open_smokeview : bool
        If True and the simulation completes, launch Smokeview interactively.
    fds_binary : str, optional
        Path to the FDS binary (falls back to config / environment).
    smv_binary : str, optional
        Path to the Smokeview binary (falls back to environment).
    max_processes : int
        MPI process count for FDS.
    timeout : float, optional
        Wall-clock seconds before FDS is killed.
    validate_before_run : bool
        If True (default) abort on validation errors.
    """

    def __init__(
        self,
        output_dir: str = "output",
        run_simulations: bool = True,
        open_smokeview: bool = False,
        fds_binary: Optional[str] = None,
        smv_binary: Optional[str] = None,
        max_processes: int = 1,
        timeout: Optional[float] = None,
        validate_before_run: bool = True,
    ) -> None:
        self.output_dir        = Path(output_dir)
        self.run_simulations   = run_simulations
        self.open_smokeview    = open_smokeview
        self.fds_binary        = fds_binary
        self.smv_binary        = smv_binary
        self.max_processes     = max_processes
        self.timeout           = timeout
        self.validate_before_run = validate_before_run

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, project) -> OrchestratorResult:
        """
        Execute the full pipeline for *project*.

        Parameters
        ----------
        project : FdsProject
            The domain model instance to simulate.

        Returns
        -------
        OrchestratorResult
        """
        from pyfds.io.fds_writer import FdsWriter
        from pyfds.validation.engine import ValidationEngine
        from pyfds.execution.runner import SimulationRunner
        from pyfds.results.indexer import ResultIndex
        from pyfds.core.events import get_global_bus, EventType

        bus = get_global_bus()
        result = OrchestratorResult()
        t0 = time.monotonic()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        chid = getattr(project, "chid", "pyfds_case") or "pyfds_case"
        fds_path = self.output_dir / f"{chid}.fds"
        result.fds_filepath = str(fds_path)
        result.output_dir   = str(self.output_dir)

        # ── Step 1: Validate ────────────────────────────────────────────────
        logger.info("Orchestrator: validating %s", chid)
        try:
            engine = ValidationEngine.default()
            report = engine.validate(project)
            result.validation_passed  = report.passed
            result.validation_summary = report.summary()
            bus.emit(EventType.VALIDATION_PASSED if report.passed
                     else EventType.VALIDATION_FAILED,
                     report, source="ScenarioOrchestrator")
            if not report.passed and self.validate_before_run:
                logger.error("Orchestrator: validation failed — aborting\n%s",
                             report.summary())
                result.error = "Validation failed: " + report.summary()
                return result
        except Exception as exc:
            logger.error("Orchestrator: validation error: %s", exc)
            result.error = str(exc)
            return result

        # ── Step 2: Write .fds file ─────────────────────────────────────────
        logger.info("Orchestrator: writing %s", fds_path)
        try:
            FdsWriter().write(project, str(fds_path))
        except Exception as exc:
            logger.error("Orchestrator: writer failed: %s", exc)
            result.error = str(exc)
            return result

        if not self.run_simulations:
            result.success = True
            result.wall_time_seconds = time.monotonic() - t0
            logger.info("Orchestrator: run_simulations=False — stopping after write")
            return result

        # ── Step 3: Run FDS ─────────────────────────────────────────────────
        logger.info("Orchestrator: launching FDS for %s", fds_path)
        try:
            runner = SimulationRunner(fds_binary=self.fds_binary)
            # Propagate OMP_NUM_THREADS when openmp_threads is configured
            env_overrides: dict = {}
            omp = getattr(getattr(project, "misc", None), "openmp_threads", None)
            if omp is not None:
                env_overrides["OMP_NUM_THREADS"] = str(omp)
            rc = runner.run_blocking(
                str(fds_path),
                num_processes=self.max_processes,
                timeout=self.timeout,
                env_overrides=env_overrides or None,
            )
            result.return_code = rc
            result.success     = (rc == 0)
            if runner.fds_error:
                result.error = runner.fds_error
        except Exception as exc:
            logger.error("Orchestrator: FDS execution error: %s", exc)
            result.error = str(exc)
            result.wall_time_seconds = time.monotonic() - t0
            return result

        # ── Step 4: Collect results ─────────────────────────────────────────
        logger.info("Orchestrator: indexing results in %s", self.output_dir)
        try:
            idx = ResultIndex.build(str(self.output_dir), chid=chid)
            result.stats = idx.stats
        except Exception as exc:
            logger.warning("Orchestrator: result indexing failed: %s", exc)

        result.wall_time_seconds = time.monotonic() - t0
        bus.emit(EventType.JOB_COMPLETED, result, source="ScenarioOrchestrator")
        logger.info("Orchestrator: finished %s  success=%s  wall=%.1fs",
                    chid, result.success, result.wall_time_seconds)

        # ── Step 5: Launch Smokeview (optional) ─────────────────────────────
        if result.success and self.open_smokeview:
            smv_path = self.output_dir / f"{chid}.smv"
            if smv_path.exists():
                from pyfds.smokeview.runner import SmokeviewRunner
                try:
                    SmokeviewRunner(smv_binary=self.smv_binary).open(
                        str(smv_path), blocking=False
                    )
                except Exception as exc:
                    logger.warning("Orchestrator: failed to launch Smokeview: %s", exc)

        return result
