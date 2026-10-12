"""
PyFDS Workflow Engine
=====================
A lightweight, composable workflow system built around the ``WorkflowStep``
Protocol.  Steps are chained into a ``WorkflowEngine`` which executes them
in order, passing a shared ``WorkflowContext`` between steps.

Built-in steps
--------------
ValidateStep        — run the validation engine on the project
WriteStep           — write the project to a .fds file
RunStep             — execute FDS via SimulationRunner
RenderStep          — launch Smokeview headless rendering via SSF script
CollectResultsStep  — build a ResultIndex for the output directory

Custom steps can be created by implementing the WorkflowStep Protocol or
subclassing ``BaseWorkflowStep``.

Example::

    engine = WorkflowEngine()
    engine.add_step(ValidateStep())
    engine.add_step(WriteStep(output_dir="runs/case_01"))
    engine.add_step(RunStep())
    engine.add_step(CollectResultsStep())

    ctx = engine.run(project)
    print(ctx.errors, ctx.results)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context shared between steps
# ---------------------------------------------------------------------------

@dataclass
class WorkflowContext:
    """
    Mutable context bag passed between all steps in a workflow.

    Attributes
    ----------
    project : object
        The ``FdsProject`` being processed.
    output_dir : str
        Base output directory set by the first WriteStep.
    fds_filepath : str
        Path to the written ``.fds`` file (set by WriteStep).
    results : dict
        Arbitrary key-value store for inter-step data sharing.
    errors : list[str]
        Accumulated error messages from failed steps.
    warnings : list[str]
        Non-fatal warnings.
    stop : bool
        If set to True by any step, the engine stops immediately.
    wall_times : dict[str, float]
        Per-step wall-clock times in seconds.
    """
    project: Any
    output_dir: str = ""
    fds_filepath: str = ""
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stop: bool = False
    wall_times: Dict[str, float] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return not self.errors and not self.stop


# ---------------------------------------------------------------------------
# WorkflowStep Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class WorkflowStep(Protocol):
    """
    Protocol that every workflow step must implement.

    A step receives the shared ``WorkflowContext``, modifies it, and
    returns it (or the same instance).  Steps must be idempotent with
    respect to context modification (i.e. they should not assume they
    are called only once).
    """
    name: str

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        ...


# ---------------------------------------------------------------------------
# BaseWorkflowStep — convenience mixin
# ---------------------------------------------------------------------------

class BaseWorkflowStep:
    """Optional base class; provides timing and logging scaffolding."""
    name: str = "base"

    def execute(self, ctx: WorkflowContext) -> WorkflowContext:
        t0 = time.monotonic()
        logger.info("WorkflowStep[%s]: starting", self.name)
        try:
            ctx = self._run(ctx)
        except Exception as exc:
            ctx.errors.append(f"{self.name}: {exc}")
            ctx.stop = True
            logger.error("WorkflowStep[%s]: unhandled error: %s", self.name, exc)
        finally:
            elapsed = time.monotonic() - t0
            ctx.wall_times[self.name] = elapsed
            logger.info("WorkflowStep[%s]: done in %.2fs", self.name, elapsed)
        return ctx

    def _run(self, ctx: WorkflowContext) -> WorkflowContext:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Built-in steps
# ---------------------------------------------------------------------------

class ValidateStep(BaseWorkflowStep):
    """
    Run the ValidationEngine on ``ctx.project``.

    Parameters
    ----------
    abort_on_error : bool
        If True (default), set ``ctx.stop=True`` on validation errors.
    """
    name = "validate"

    def __init__(self, abort_on_error: bool = True) -> None:
        self.abort_on_error = abort_on_error

    def _run(self, ctx: WorkflowContext) -> WorkflowContext:
        from pyfds.validation.engine import ValidationEngine
        report = ValidationEngine.default().validate(ctx.project)
        ctx.results["validation_report"] = report
        if not report.passed:
            msg = f"Validation failed: {report.summary()}"
            ctx.warnings.append(msg) if not self.abort_on_error else ctx.errors.append(msg)
            if self.abort_on_error:
                ctx.stop = True
            logger.warning("ValidateStep: %s", msg)
        else:
            logger.info("ValidateStep: passed (%d warnings)", len(report.warnings))
        return ctx


class WriteStep(BaseWorkflowStep):
    """
    Write ``ctx.project`` to a ``.fds`` file.

    Parameters
    ----------
    output_dir : str
        Directory in which to create the ``.fds`` file.
    filename : str, optional
        Override filename; default is ``<project.chid>.fds``.
    """
    name = "write"

    def __init__(self, output_dir: str = "output", filename: Optional[str] = None) -> None:
        self._output_dir = output_dir
        self._filename   = filename

    def _run(self, ctx: WorkflowContext) -> WorkflowContext:
        from pyfds.io.fds_writer import FdsWriter
        chid     = getattr(ctx.project, "chid", "pyfds_case") or "pyfds_case"
        out_dir  = Path(self._output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = self._filename or f"{chid}.fds"
        fds_path = out_dir / filename
        FdsWriter().write(ctx.project, str(fds_path))
        ctx.fds_filepath = str(fds_path)
        ctx.output_dir   = str(out_dir)
        ctx.results["fds_filepath"] = str(fds_path)
        logger.info("WriteStep: wrote %s", fds_path)
        return ctx


class RunStep(BaseWorkflowStep):
    """
    Execute FDS on ``ctx.fds_filepath``.

    Parameters
    ----------
    fds_binary : str, optional
        Path to FDS binary.
    num_processes : int
        MPI process count.
    timeout : float, optional
        Wall-clock time limit in seconds.
    """
    name = "run"

    def __init__(
        self,
        fds_binary: Optional[str] = None,
        num_processes: int = 1,
        timeout: Optional[float] = None,
    ) -> None:
        self.fds_binary    = fds_binary
        self.num_processes = num_processes
        self.timeout       = timeout

    def _run(self, ctx: WorkflowContext) -> WorkflowContext:
        from pyfds.execution.runner import SimulationRunner
        if not ctx.fds_filepath:
            ctx.errors.append("RunStep: no fds_filepath in context (WriteStep must run first)")
            ctx.stop = True
            return ctx
        runner = SimulationRunner(fds_binary=self.fds_binary)
        rc = runner.run_blocking(
            ctx.fds_filepath,
            num_processes=self.num_processes,
            timeout=self.timeout,
        )
        ctx.results["return_code"] = rc
        if rc != 0:
            ctx.errors.append(f"RunStep: FDS exited with code {rc}")
            ctx.stop = True
        logger.info("RunStep: FDS rc=%d", rc)
        return ctx


class RenderStep(BaseWorkflowStep):
    """
    Run Smokeview headless rendering for a sequence of times.

    Parameters
    ----------
    times : list[float]
        Simulation times at which to capture screenshots.
    quantity : str
        Slice quantity to render.
    smv_binary : str, optional
        Path to Smokeview binary.
    image_format : str
        ``"png"`` or ``"jpg"``.
    """
    name = "render"

    def __init__(
        self,
        times: Optional[List[float]] = None,
        quantity: str = "TEMPERATURE",
        smv_binary: Optional[str] = None,
        image_format: str = "png",
    ) -> None:
        self.times        = times or []
        self.quantity     = quantity
        self.smv_binary   = smv_binary
        self.image_format = image_format

    def _run(self, ctx: WorkflowContext) -> WorkflowContext:
        from pyfds.smokeview.runner import SmokeviewRunner
        if not ctx.output_dir:
            ctx.warnings.append("RenderStep: no output_dir — skipping render")
            return ctx

        chid = getattr(ctx.project, "chid", "pyfds_case") or "pyfds_case"
        smv_path = Path(ctx.output_dir) / f"{chid}.smv"
        if not smv_path.exists():
            ctx.warnings.append(f"RenderStep: SMV file not found: {smv_path}")
            return ctx

        runner = SmokeviewRunner(smv_binary=self.smv_binary)
        image_paths = runner.capture_screenshots(
            str(smv_path),
            self.times,
            quantity=self.quantity,
            output_dir=ctx.output_dir,
            image_format=self.image_format,
        )
        ctx.results["screenshot_paths"] = image_paths
        logger.info("RenderStep: captured %d screenshots", len(image_paths))
        return ctx


class CollectResultsStep(BaseWorkflowStep):
    """
    Build a ``ResultIndex`` for the simulation output directory.

    Stores the index under ``ctx.results['result_index']``.
    """
    name = "collect_results"

    def _run(self, ctx: WorkflowContext) -> WorkflowContext:
        from pyfds.results.indexer import ResultIndex
        if not ctx.output_dir:
            ctx.warnings.append("CollectResultsStep: no output_dir — skipping")
            return ctx
        chid = getattr(ctx.project, "chid", "pyfds_case") or "pyfds_case"
        idx  = ResultIndex.build(ctx.output_dir, chid=chid)
        ctx.results["result_index"] = idx
        logger.info("CollectResultsStep: %s", idx.summary())
        return ctx


# ---------------------------------------------------------------------------
# WorkflowEngine
# ---------------------------------------------------------------------------

class WorkflowEngine:
    """
    Executes a sequence of ``WorkflowStep`` objects in order.

    Stops immediately if any step sets ``ctx.stop = True``.

    Example::

        engine = WorkflowEngine()
        engine.add_step(ValidateStep())
        engine.add_step(WriteStep(output_dir="output/case_01"))
        engine.add_step(RunStep())
        engine.add_step(CollectResultsStep())

        ctx = engine.run(project)
        if ctx.success:
            idx = ctx.results["result_index"]
    """

    def __init__(self) -> None:
        self._steps: List[WorkflowStep] = []

    def add_step(self, step: WorkflowStep) -> "WorkflowEngine":
        """Append *step* to the pipeline. Returns self for chaining."""
        self._steps.append(step)
        return self

    def run(self, project: Any) -> WorkflowContext:
        """
        Execute all steps sequentially on *project*.

        Returns the populated ``WorkflowContext``.
        """
        ctx = WorkflowContext(project=project)
        for step in self._steps:
            if ctx.stop:
                logger.info("WorkflowEngine: stopping after step error, skipping %s",
                            getattr(step, "name", "?"))
                break
            ctx = step.execute(ctx)
        if ctx.success:
            logger.info("WorkflowEngine: all steps completed successfully")
        else:
            logger.error("WorkflowEngine: workflow failed: %s", ctx.errors)
        return ctx

    def step_names(self) -> List[str]:
        return [getattr(s, "name", "?") for s in self._steps]

    def __repr__(self) -> str:
        return f"<WorkflowEngine steps={self.step_names()}>"
