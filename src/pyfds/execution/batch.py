"""
PyFDS Batch / Parametric Study System
======================================
Generate and execute a grid of FDS variants by varying one or more
project parameters programmatically.

Usage::

    from pyfds.execution.batch import ParametricStudy, BatchExecutor

    study = ParametricStudy("hrr_sensitivity")
    study.base_fds_file = "base_case.fds"
    study.vary("params.t_end", [30.0, 60.0, 120.0])
    study.vary("misc.tmpa",    [15.0, 20.0, 25.0])   # 3×3 = 9 variants

    executor = BatchExecutor(output_root="batch_results/", max_workers=4)
    report   = executor.run(study)
    print(report.summary())
"""
from __future__ import annotations

import itertools
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .job import Job, JobStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter space definition
# ---------------------------------------------------------------------------

@dataclass
class ParameterAxis:
    """One parameter and the values it will take across the study."""
    path: str               # dot-separated path e.g. "params.t_end", "misc.tmpa"
    values: List[Any]
    label: Optional[str] = None     # human-readable label (default = path)

    @property
    def name(self) -> str:
        return self.label or self.path


@dataclass
class StudyVariant:
    """One specific combination of parameter values."""
    name: str
    overrides: Dict[str, Any]       # path → value
    fds_filepath: Optional[str] = None


@dataclass
class BatchReport:
    """Summary of a completed batch execution."""
    study_name: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    elapsed_seconds: float = 0.0
    variant_results: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.completed / self.total * 100) if self.total else 0.0

    def summary(self) -> str:
        return (f"Batch '{self.study_name}': {self.completed}/{self.total} completed, "
                f"{self.failed} failed in {self.elapsed_seconds:.1f}s "
                f"({self.success_rate:.0f}% success)")


# ---------------------------------------------------------------------------
# ParametricStudy
# ---------------------------------------------------------------------------

class ParametricStudy:
    """
    Defines a factorial grid of FDS variants.

    Parameters
    ----------
    name : str
        Identifier for this study (used in output directory naming).
    base_fds_file : str
        Path to the base .fds file that all variants start from.
    """

    def __init__(self, name: str, base_fds_file: str = "") -> None:
        self.name = name
        self.base_fds_file = base_fds_file
        self._axes: List[ParameterAxis] = []
        self._fixed: Dict[str, Any] = {}
        self._custom_variants: List[StudyVariant] = []

    # ── Parameter definition ─────────────────────────────────────────────────

    def vary(self, path: str, values: List[Any], label: Optional[str] = None) -> None:
        """
        Add a parameter axis.

        Parameters
        ----------
        path:
            Dot-separated path to the parameter on FdsProject, e.g.
            ``"params.t_end"`` or ``"misc.tmpa"``.
        values:
            List of values the parameter takes.
        label:
            Optional human-readable axis name.
        """
        self._axes.append(ParameterAxis(path=path, values=values, label=label))

    def fix(self, path: str, value: Any) -> None:
        """Set a parameter that is fixed (same for all variants)."""
        self._fixed[path] = value

    def add_variant(self, name: str, **overrides: Any) -> None:
        """
        Manually add a specific variant (bypasses factorial expansion).

        Useful for adding corner cases or previously interesting points.
        """
        self._custom_variants.append(
            StudyVariant(name=name, overrides=overrides)
        )

    # ── Expansion ────────────────────────────────────────────────────────────

    def expand(self) -> List[StudyVariant]:
        """
        Generate all variants as a Cartesian product of the parameter axes,
        plus any manually-added custom variants.
        """
        variants: List[StudyVariant] = []

        if self._axes:
            axis_names = [ax.name for ax in self._axes]
            for combo in itertools.product(*[ax.values for ax in self._axes]):
                overrides = dict(self._fixed)
                overrides.update(dict(zip([ax.path for ax in self._axes], combo)))
                name_parts = [f"{n}={v}" for n, v in zip(axis_names, combo)]
                variant_name = f"{self.name}_{'_'.join(name_parts)}"
                # Sanitize for use as a filename
                variant_name = variant_name.replace(".", "_").replace(" ", "_")
                variants.append(StudyVariant(name=variant_name, overrides=overrides))
        elif self._fixed:
            variants.append(StudyVariant(name=self.name, overrides=dict(self._fixed)))

        variants.extend(self._custom_variants)
        return variants

    @property
    def variant_count(self) -> int:
        return len(self.expand())

    def __repr__(self) -> str:
        return (f"<ParametricStudy name={self.name!r} "
                f"axes={len(self._axes)} variants={self.variant_count}>")


# ---------------------------------------------------------------------------
# BatchExecutor
# ---------------------------------------------------------------------------

class BatchExecutor:
    """
    Generates, saves, and optionally runs all variants of a ``ParametricStudy``.

    Parameters
    ----------
    output_root : str
        Root directory where variant sub-folders are created.
    max_workers : int
        Maximum concurrent FDS processes (passed to ``JobQueue``).
    run_simulations : bool
        If False, only generates the .fds files without running FDS.
        Useful for reviewing the generated variants before committing.
    fds_binary : Optional[str]
        Override path to the FDS binary.
    """

    def __init__(
        self,
        output_root: str = "batch_results",
        max_workers: int = 2,
        run_simulations: bool = True,
        fds_binary: Optional[str] = None,
    ) -> None:
        self.output_root = Path(output_root)
        self.max_workers = max_workers
        self.run_simulations = run_simulations
        self.fds_binary = fds_binary

    def run(self, study: ParametricStudy) -> BatchReport:
        """
        Execute all variants of *study* and return a ``BatchReport``.

        Steps:
          1. Load base .fds file into ``FdsProject``.
          2. For each variant, apply overrides, save to a sub-directory.
          3. Submit all saved .fds files to the ``JobQueue`` (if ``run_simulations``).
          4. Wait for all jobs; compile report.
        """
        from pyfds.io.fds_parser import FdsParser
        from pyfds.io.fds_writer import FdsWriter
        from pyfds.core.events import get_global_bus, EventType

        bus = get_global_bus()
        t0 = time.monotonic()
        variants = study.expand()
        report = BatchReport(study_name=study.name, total=len(variants))

        bus.emit(EventType.BATCH_STARTED,
                 {"study": study.name, "total": len(variants)},
                 source="BatchExecutor")
        logger.info("BatchExecutor: starting %s (%d variants)", study.name, len(variants))

        # Load base project
        base_project = None
        if study.base_fds_file:
            try:
                base_project = FdsParser().parse(study.base_fds_file)
            except Exception as exc:
                logger.error("Failed to parse base file: %s", exc)

        writer = FdsWriter()
        jobs: List[Job] = []

        for variant in variants:
            variant_dir = self.output_root / study.name / variant.name
            variant_dir.mkdir(parents=True, exist_ok=True)
            out_fds = variant_dir / f"{variant.name}.fds"

            # Clone and apply overrides
            try:
                project = self._clone_and_apply(base_project, variant.overrides)
                project.chid = variant.name[:63]   # FDS CHID limit
                writer.write(project, str(out_fds))
                variant.fds_filepath = str(out_fds)
                logger.debug("BatchExecutor: wrote %s", out_fds)
            except Exception as exc:
                logger.error("BatchExecutor: failed to write variant %s: %s",
                             variant.name, exc)
                report.failed += 1
                report.variant_results.append({
                    "name": variant.name, "status": "WRITE_ERROR", "error": str(exc)
                })
                continue

            if self.run_simulations:
                job = Job(
                    fds_filepath=str(out_fds),
                    output_directory=str(variant_dir),
                    tags={"study": study.name, "variant": variant.name},
                )
                jobs.append(job)

        if self.run_simulations and jobs:
            self._run_jobs(jobs, report, bus, study.name)

        elapsed = time.monotonic() - t0
        report.elapsed_seconds = elapsed
        bus.emit(EventType.BATCH_COMPLETED, report, source="BatchExecutor")
        logger.info("BatchExecutor: %s", report.summary())
        return report

    def _clone_and_apply(self, base_project, overrides: Dict[str, Any]):
        """Deep-clone the base project and apply dot-path overrides."""
        from pyfds.domain.model import FdsProject
        from pyfds.io.serializer import Serializer

        if base_project is None:
            project = FdsProject()
        else:
            # Round-trip through JSON for a clean deep copy
            ser = Serializer()
            project = ser.load_string(ser.save_string(base_project))

        for path, value in overrides.items():
            self._set_nested(project, path, value)

        return project

    def _set_nested(self, obj: Any, path: str, value: Any) -> None:
        """Apply a dot-separated attribute path like 'params.t_end'."""
        parts = path.split(".")
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)

    def _run_jobs(self, jobs: List[Job], report: BatchReport,
                  bus, study_name: str) -> None:
        from .queue import JobQueue
        from pyfds.core.events import EventType

        q = JobQueue(max_workers=self.max_workers, fds_binary=self.fds_binary)
        q.start()

        for job in jobs:
            q.submit(job)

        q.wait_all()
        q.stop(wait=False)

        for job in jobs:
            result = {
                "name":      job.tags.get("variant", job.job_id[:8]),
                "status":    job.status.name,
                "wall_time": job.wall_time,
                "fds_file":  job.fds_filepath,
            }
            report.variant_results.append(result)
            if job.status == JobStatus.COMPLETED:
                report.completed += 1
                bus.emit(EventType.BATCH_VARIANT_DONE,
                         {"variant": job.tags.get("variant"), "success": True},
                         source="BatchExecutor")
            elif job.status == JobStatus.FAILED:
                report.failed += 1
                result["error"] = job.error_message
            elif job.status == JobStatus.CANCELLED:
                report.cancelled += 1
