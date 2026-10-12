"""Unit tests — pyfds.execution.queue (JobQueue, _QueueEntry)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from pyfds.execution.job import Job, JobStatus
from pyfds.execution.queue import JobQueue, _QueueEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job(filepath="case.fds", priority=5, **kwargs) -> Job:
    return Job(fds_filepath=filepath, output_directory="out/",
               priority=priority, **kwargs)


# ---------------------------------------------------------------------------
# _QueueEntry ordering
# ---------------------------------------------------------------------------

class TestQueueEntry:
    def test_lower_priority_sorts_first(self):
        e1 = _QueueEntry(_job(priority=1), seq=1)
        e2 = _QueueEntry(_job(priority=9), seq=2)
        assert e1 < e2

    def test_same_priority_insertion_order_tiebreak(self):
        e1 = _QueueEntry(_job(priority=5), seq=1)
        e2 = _QueueEntry(_job(priority=5), seq=2)
        assert e1 < e2


# ---------------------------------------------------------------------------
# JobQueue — submit and query (no worker threads started)
# ---------------------------------------------------------------------------

class TestJobQueueSubmitQuery:
    def test_submit_returns_job_id(self):
        q = JobQueue()
        j = _job()
        job_id = q.submit(j)
        assert job_id == j.job_id

    def test_get_job_after_submit(self):
        q = JobQueue()
        j = _job()
        q.submit(j)
        assert q.get_job(j.job_id) is j

    def test_all_jobs_returns_submitted(self):
        q = JobQueue()
        j1 = _job("a.fds")
        j2 = _job("b.fds")
        q.submit(j1)
        q.submit(j2)
        ids = {j.job_id for j in q.all_jobs()}
        assert j1.job_id in ids
        assert j2.job_id in ids

    def test_pending_jobs_returns_pending(self):
        q = JobQueue()
        j = _job()
        q.submit(j)
        assert j in q.pending_jobs()

    def test_running_jobs_empty_without_workers(self):
        q = JobQueue()
        q.submit(_job())
        assert q.running_jobs() == []

    def test_queue_depth_reflects_submitted(self):
        q = JobQueue()
        q.submit(_job("a.fds"))
        q.submit(_job("b.fds"))
        assert q.queue_depth >= 1

    def test_get_job_unknown_returns_none(self):
        q = JobQueue()
        assert q.get_job("unknown-id") is None


# ---------------------------------------------------------------------------
# JobQueue — cancel pending
# ---------------------------------------------------------------------------

class TestJobQueueCancel:
    def test_cancel_pending_job(self):
        q = JobQueue()
        j = _job()
        q.submit(j)
        result = q.cancel(j.job_id)
        assert result is True
        assert j.status == JobStatus.CANCELLED

    def test_cancel_unknown_returns_false(self):
        q = JobQueue()
        assert q.cancel("no-such-id") is False

    def test_cancel_all(self):
        q = JobQueue()
        j1 = _job("a.fds")
        j2 = _job("b.fds")
        q.submit(j1)
        q.submit(j2)
        q.cancel_all()
        for j in [j1, j2]:
            assert j.is_terminal


# ---------------------------------------------------------------------------
# JobQueue — callbacks
# ---------------------------------------------------------------------------

class TestJobQueueCallbacks:
    def test_on_job_complete_registered(self):
        q = JobQueue()
        cb = MagicMock()
        q.on_job_complete(cb)
        assert cb in q._on_complete_callbacks


# ---------------------------------------------------------------------------
# JobQueue — start/stop
# ---------------------------------------------------------------------------

class TestJobQueueLifecycle:
    def test_start_creates_workers(self):
        q = JobQueue(max_workers=2)
        q.start()
        try:
            assert len(q._workers) == 2
        finally:
            q.stop(wait=True)

    def test_stop_clears_workers(self):
        q = JobQueue(max_workers=1)
        q.start()
        q.stop(wait=True)
        assert len(q._workers) == 0

    def test_start_stop_no_jobs(self):
        q = JobQueue(max_workers=1)
        q.start()
        q.stop(wait=True)


# ---------------------------------------------------------------------------
# wait_all — exits immediately when all jobs are terminal
# ---------------------------------------------------------------------------

class TestWaitAll:
    def test_wait_all_returns_immediately_if_no_jobs(self):
        q = JobQueue()
        q.wait_all(poll_interval=0.01)

    def test_wait_all_returns_when_all_terminal(self):
        q = JobQueue()
        j = _job()
        q.submit(j)
        j.mark_cancelled()
        q.wait_all(poll_interval=0.01)
