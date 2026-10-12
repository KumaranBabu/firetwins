"""
PyFDS Job Model
===============
Represents a single FDS simulation execution with full lifecycle tracking.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional


class JobStatus(Enum):
    PENDING    = auto()
    RUNNING    = auto()
    COMPLETED  = auto()
    FAILED     = auto()
    CANCELLED  = auto()
    TIMEOUT    = auto()


@dataclass
class JobMetrics:
    """Runtime performance metrics collected during execution."""
    wall_time_seconds: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    sim_time_reached: float = 0.0
    step_count: int = 0


@dataclass
class Job:
    """
    Represents one FDS simulation run.

    Attributes
    ----------
    job_id : str
        Globally unique identifier.
    fds_filepath : str
        Path to the .fds input file.
    output_directory : str
        Where FDS writes its output files.
    num_processes : int
        MPI process count.
    priority : int
        Lower value = higher priority in the queue (default 5).
    timeout : Optional[float]
        Maximum allowed wall-clock seconds, or None for no limit.
    tags : Dict[str, str]
        Arbitrary metadata for grouping/filtering batch results.
    """
    fds_filepath: str
    output_directory: str
    num_processes: int = 1
    priority: int = 5
    timeout: Optional[float] = None
    tags: Dict[str, str] = field(default_factory=dict)

    # Auto-generated
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.monotonic)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    return_code: Optional[int] = None
    error_message: Optional[str] = None
    stdout_lines: List[str] = field(default_factory=list)
    metrics: JobMetrics = field(default_factory=JobMetrics)

    # ── Lifecycle helpers ────────────────────────────────────────────────────

    def mark_started(self) -> None:
        self.status = JobStatus.RUNNING
        self.started_at = time.monotonic()

    def mark_completed(self, return_code: int) -> None:
        self.return_code = return_code
        self.finished_at = time.monotonic()
        self.status = JobStatus.COMPLETED if return_code == 0 else JobStatus.FAILED
        if self.started_at:
            self.metrics.wall_time_seconds = self.finished_at - self.started_at

    def mark_failed(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error_message = error
        self.finished_at = time.monotonic()
        if self.started_at:
            self.metrics.wall_time_seconds = self.finished_at - self.started_at

    def mark_cancelled(self) -> None:
        self.status = JobStatus.CANCELLED
        self.finished_at = time.monotonic()

    def mark_timeout(self) -> None:
        self.status = JobStatus.TIMEOUT
        self.finished_at = time.monotonic()
        self.error_message = f"Exceeded timeout of {self.timeout}s"

    # ── Queries ──────────────────────────────────────────────────────────────

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED,
                               JobStatus.CANCELLED, JobStatus.TIMEOUT)

    @property
    def wall_time(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None

    @property
    def chid(self) -> str:
        return Path(self.fds_filepath).stem

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id":         self.job_id,
            "chid":           self.chid,
            "fds_filepath":   self.fds_filepath,
            "output_dir":     self.output_directory,
            "num_processes":  self.num_processes,
            "status":         self.status.name,
            "priority":       self.priority,
            "created_at":     self.created_at,
            "started_at":     self.started_at,
            "finished_at":    self.finished_at,
            "return_code":    self.return_code,
            "error_message":  self.error_message,
            "wall_time_s":    self.wall_time,
            "tags":           self.tags,
        }

    def __repr__(self) -> str:
        return f"<Job id={self.job_id[:8]} chid={self.chid!r} status={self.status.name}>"

    # Comparison for priority queue ordering
    def __lt__(self, other: "Job") -> bool:
        return self.priority < other.priority
