"""
PyFDS Job Queue
===============
Thread-safe priority job queue with a configurable worker pool.

Usage::

    queue = JobQueue(max_workers=4)
    queue.start()

    job = Job(fds_filepath="case.fds", output_directory="out/")
    queue.submit(job)

    queue.wait_all()
    queue.stop()

GUI contract:
    ``JobQueue`` emits ``JOB_QUEUED``, ``JOB_STARTED``, ``JOB_COMPLETED``,
    and ``JOB_FAILED`` events through the global EventBus.
    A future GUI subscribes to those events to update a job-status panel.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Dict, List, Optional

from .job import Job, JobStatus
from .runner import SimulationRunner

logger = logging.getLogger(__name__)


class _QueueEntry:
    """Wrapper to make Job sortable by priority in heapq."""
    __slots__ = ("priority", "seq", "job")

    def __init__(self, job: Job, seq: int) -> None:
        self.priority = job.priority
        self.seq = seq                  # tiebreak by insertion order
        self.job = job

    def __lt__(self, other: "_QueueEntry") -> bool:
        return (self.priority, self.seq) < (other.priority, other.seq)


class JobQueue:
    """
    Priority-based simulation job queue backed by a thread-pool executor.

    Parameters
    ----------
    max_workers : int
        Maximum number of concurrent FDS processes.
    fds_binary : Optional[str]
        Path to FDS binary; falls back to config then environment.
    mpiexec_binary : Optional[str]
        Path to mpiexec; falls back to config then environment.
    """

    def __init__(
        self,
        max_workers: int = 2,
        fds_binary: Optional[str] = None,
        mpiexec_binary: Optional[str] = None,
    ) -> None:
        self._max_workers = max_workers
        self._fds_binary = fds_binary
        self._mpiexec_binary = mpiexec_binary

        self._pqueue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = 0
        self._lock = threading.Lock()

        self._jobs: Dict[str, Job] = {}             # all known jobs
        self._workers: List[threading.Thread] = []
        self._stop_event = threading.Event()
        self._active_runners: Dict[str, SimulationRunner] = {}  # job_id → runner

        self._on_complete_callbacks: List[Callable[[Job], None]] = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the worker pool threads."""
        self._stop_event.clear()
        for i in range(self._max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"pyfds-queue-worker-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)
        logger.info("JobQueue started (%d workers)", self._max_workers)

    def stop(self, wait: bool = True) -> None:
        """Signal workers to stop. If wait=True, block until they finish."""
        self._stop_event.set()
        # Unblock each worker with a sentinel
        for _ in self._workers:
            self._pqueue.put(_QueueEntry(
                Job(fds_filepath="__sentinel__", output_directory=""),
                self._next_seq()
            ))
        if wait:
            for t in self._workers:
                t.join(timeout=5)
        self._workers.clear()
        logger.info("JobQueue stopped")

    # ── Submission ────────────────────────────────────────────────────────────

    def submit(self, job: Job) -> str:
        """
        Enqueue *job* for execution.

        Returns the job_id.
        """
        with self._lock:
            self._jobs[job.job_id] = job
            entry = _QueueEntry(job, self._next_seq())
        self._pqueue.put(entry)
        self._emit(EventType.JOB_QUEUED, job)
        logger.debug("JobQueue: submitted %s (priority=%d)", job.job_id[:8], job.priority)
        return job.job_id

    def cancel(self, job_id: str) -> bool:
        """
        Request cancellation of *job_id*.

        If the job is still PENDING it is simply marked CANCELLED.
        If it is RUNNING the underlying ``SimulationRunner.cancel()`` is called.
        Returns True if the job was found.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status == JobStatus.PENDING:
                job.mark_cancelled()
                self._emit(EventType.JOB_CANCELLED, job)
                return True
            runner = self._active_runners.get(job_id)
        if runner:
            runner.cancel()
        return True

    def cancel_all(self) -> None:
        """Cancel every pending and running job."""
        with self._lock:
            ids = list(self._jobs.keys())
        for job_id in ids:
            self.cancel(job_id)

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def all_jobs(self) -> List[Job]:
        with self._lock:
            return list(self._jobs.values())

    def pending_jobs(self) -> List[Job]:
        return [j for j in self.all_jobs() if j.status == JobStatus.PENDING]

    def running_jobs(self) -> List[Job]:
        return [j for j in self.all_jobs() if j.status == JobStatus.RUNNING]

    @property
    def queue_depth(self) -> int:
        return self._pqueue.qsize()

    def wait_all(self, poll_interval: float = 1.0) -> None:
        """Block until all submitted jobs reach a terminal state."""
        while True:
            with self._lock:
                active = [j for j in self._jobs.values() if not j.is_terminal]
            if not active:
                break
            time.sleep(poll_interval)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def on_job_complete(self, callback: Callable[[Job], None]) -> None:
        """Register a callback invoked when any job reaches a terminal state."""
        self._on_complete_callbacks.append(callback)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                entry = self._pqueue.get(timeout=1.0)
            except queue.Empty:
                continue

            job = entry.job
            if job.fds_filepath == "__sentinel__":
                break
            if job.is_terminal:
                self._pqueue.task_done()
                continue

            # Execute the job
            runner = SimulationRunner(
                fds_binary=self._fds_binary,
                mpiexec_binary=self._mpiexec_binary,
            )
            with self._lock:
                self._active_runners[job.job_id] = runner
            job.mark_started()
            self._emit(EventType.JOB_STARTED, job)

            def _line(line: str, _job=job) -> None:
                _job.stdout_lines.append(line)

            rc = runner.run_blocking(
                job.fds_filepath,
                num_processes=job.num_processes,
                on_line=_line,
                timeout=job.timeout,
            )
            job.mark_completed(rc)

            with self._lock:
                self._active_runners.pop(job.job_id, None)

            self._emit(EventType.JOB_COMPLETED if job.status == JobStatus.COMPLETED
                       else EventType.JOB_FAILED, job)

            for cb in self._on_complete_callbacks:
                try:
                    cb(job)
                except Exception as exc:
                    logger.error("JobQueue callback error: %s", exc)

            self._pqueue.task_done()

    def _emit(self, event_type, payload) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            get_global_bus().emit(event_type, payload, source="JobQueue")
        except Exception:
            pass


# Lazy import to avoid circular at module level
try:
    from pyfds.core.events import EventType
except ImportError:
    class EventType:  # type: ignore[no-redef]
        JOB_QUEUED = "JOB_QUEUED"
        JOB_STARTED = "JOB_STARTED"
        JOB_COMPLETED = "JOB_COMPLETED"
        JOB_FAILED = "JOB_FAILED"
        JOB_CANCELLED = "JOB_CANCELLED"
