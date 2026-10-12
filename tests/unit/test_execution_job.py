"""Unit tests — pyfds.execution.job (Job, JobStatus, JobMetrics)."""
from __future__ import annotations

import time
import pytest

from pyfds.execution.job import Job, JobStatus, JobMetrics


# ---------------------------------------------------------------------------
# JobStatus
# ---------------------------------------------------------------------------

class TestJobStatus:
    def test_all_statuses_defined(self):
        statuses = [s for s in JobStatus]
        names = {s.name for s in statuses}
        assert "PENDING" in names
        assert "RUNNING" in names
        assert "COMPLETED" in names
        assert "FAILED" in names
        assert "CANCELLED" in names
        assert "TIMEOUT" in names


# ---------------------------------------------------------------------------
# JobMetrics
# ---------------------------------------------------------------------------

class TestJobMetrics:
    def test_defaults(self):
        m = JobMetrics()
        assert m.wall_time_seconds == 0.0
        assert m.cpu_percent == 0.0
        assert m.memory_mb == 0.0
        assert m.sim_time_reached == 0.0
        assert m.step_count == 0


# ---------------------------------------------------------------------------
# Job — creation
# ---------------------------------------------------------------------------

class TestJobCreation:
    def test_basic_creation(self):
        j = Job(fds_filepath="case.fds", output_directory="out/")
        assert j.fds_filepath == "case.fds"
        assert j.output_directory == "out/"

    def test_default_status_pending(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        assert j.status == JobStatus.PENDING

    def test_unique_job_ids(self):
        j1 = Job(fds_filepath="a.fds", output_directory="o/")
        j2 = Job(fds_filepath="b.fds", output_directory="o/")
        assert j1.job_id != j2.job_id

    def test_default_num_processes(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        assert j.num_processes == 1

    def test_default_priority(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        assert j.priority == 5

    def test_default_timeout_none(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        assert j.timeout is None

    def test_tags_default_empty(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        assert j.tags == {}

    def test_chid_from_filepath(self):
        j = Job(fds_filepath="/path/to/hotel_fire.fds", output_directory="o/")
        assert j.chid == "hotel_fire"


# ---------------------------------------------------------------------------
# Job — lifecycle
# ---------------------------------------------------------------------------

class TestJobLifecycle:
    def test_mark_started(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_started()
        assert j.status == JobStatus.RUNNING
        assert j.started_at is not None

    def test_mark_completed_zero_rc(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_started()
        j.mark_completed(0)
        assert j.status == JobStatus.COMPLETED
        assert j.return_code == 0
        assert j.finished_at is not None

    def test_mark_completed_nonzero_rc(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_started()
        j.mark_completed(1)
        assert j.status == JobStatus.FAILED
        assert j.return_code == 1

    def test_mark_failed(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_started()
        j.mark_failed("segfault")
        assert j.status == JobStatus.FAILED
        assert j.error_message == "segfault"
        assert j.finished_at is not None

    def test_mark_cancelled(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_cancelled()
        assert j.status == JobStatus.CANCELLED
        assert j.finished_at is not None

    def test_mark_timeout(self):
        j = Job(fds_filepath="a.fds", output_directory="o/", timeout=30.0)
        j.mark_timeout()
        assert j.status == JobStatus.TIMEOUT
        assert "30.0" in j.error_message

    def test_wall_time_calculated(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_started()
        j.mark_completed(0)
        assert j.wall_time is not None
        assert j.wall_time >= 0.0

    def test_wall_time_none_before_started(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        assert j.wall_time is None

    def test_metrics_wall_time_set_on_complete(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_started()
        j.mark_completed(0)
        assert j.metrics.wall_time_seconds >= 0.0


# ---------------------------------------------------------------------------
# Job — is_terminal
# ---------------------------------------------------------------------------

class TestJobIsTerminal:
    def test_pending_not_terminal(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        assert j.is_terminal is False

    def test_running_not_terminal(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_started()
        assert j.is_terminal is False

    def test_completed_is_terminal(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_started()
        j.mark_completed(0)
        assert j.is_terminal is True

    def test_failed_is_terminal(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_failed("err")
        assert j.is_terminal is True

    def test_cancelled_is_terminal(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        j.mark_cancelled()
        assert j.is_terminal is True

    def test_timeout_is_terminal(self):
        j = Job(fds_filepath="a.fds", output_directory="o/", timeout=10.0)
        j.mark_timeout()
        assert j.is_terminal is True


# ---------------------------------------------------------------------------
# Job — to_dict and ordering
# ---------------------------------------------------------------------------

class TestJobToDict:
    def test_to_dict_keys(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        d = j.to_dict()
        assert "job_id" in d
        assert "chid" in d
        assert "status" in d
        assert d["status"] == "PENDING"

    def test_to_dict_tags_preserved(self):
        j = Job(fds_filepath="a.fds", output_directory="o/",
                tags={"scenario": "baseline"})
        d = j.to_dict()
        assert d["tags"]["scenario"] == "baseline"

    def test_repr_contains_status(self):
        j = Job(fds_filepath="a.fds", output_directory="o/")
        assert "PENDING" in repr(j)

    def test_priority_ordering(self):
        j_lo = Job(fds_filepath="a.fds", output_directory="o/", priority=1)
        j_hi = Job(fds_filepath="b.fds", output_directory="o/", priority=9)
        assert j_lo < j_hi
