"""Unit tests — pyfds.automation.workflow (WorkflowEngine, steps)."""
from __future__ import annotations

from pathlib import Path
import pytest

from pyfds.automation.workflow import (
    WorkflowEngine, WorkflowContext, ValidateStep, WriteStep, CollectResultsStep,
)
from pyfds.domain.model import FdsProject, Mesh, Surface


def _make_simple_project():
    p = FdsProject()
    p.chid = "wf_test"
    p.add_entity(Mesh(name="m1", cell_count=(16, 16, 8),
                      x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=2))
    p.add_entity(Surface(name="inert"))
    return p


@pytest.fixture
def simple_project():
    return _make_simple_project()


# ---------------------------------------------------------------------------
# WorkflowContext
# ---------------------------------------------------------------------------

class TestWorkflowContext:
    def test_creation(self, simple_project):
        ctx = WorkflowContext(project=simple_project)
        assert ctx.project is simple_project
        assert ctx.errors == []
        assert ctx.stop is False

    def test_results_dict_initially_empty(self, simple_project):
        ctx = WorkflowContext(project=simple_project)
        assert ctx.results == {}

    def test_success_property_true_when_no_errors(self, simple_project):
        ctx = WorkflowContext(project=simple_project)
        assert ctx.success is True

    def test_success_property_false_when_errors(self, simple_project):
        ctx = WorkflowContext(project=simple_project)
        ctx.errors.append("something failed")
        assert ctx.success is False

    def test_success_false_when_stop(self, simple_project):
        ctx = WorkflowContext(project=simple_project)
        ctx.stop = True
        assert ctx.success is False


# ---------------------------------------------------------------------------
# ValidateStep
# ---------------------------------------------------------------------------

class TestValidateStep:
    def test_valid_project_does_not_stop(self, simple_project):
        step = ValidateStep(abort_on_error=True)
        ctx = WorkflowContext(project=simple_project)
        ctx = step.execute(ctx)
        assert ctx.stop is False

    def test_invalid_project_stops_pipeline_when_abort_true(self):
        p = FdsProject()  # no meshes → validation error
        p.chid = "bad"
        step = ValidateStep(abort_on_error=True)
        ctx = WorkflowContext(project=p)
        ctx = step.execute(ctx)
        assert ctx.stop is True

    def test_invalid_project_continues_when_abort_false(self):
        p = FdsProject()
        p.chid = "bad"
        step = ValidateStep(abort_on_error=False)
        ctx = WorkflowContext(project=p)
        ctx = step.execute(ctx)
        assert ctx.stop is False

    def test_validation_report_stored_in_results(self, simple_project):
        step = ValidateStep()
        ctx = WorkflowContext(project=simple_project)
        ctx = step.execute(ctx)
        assert "validation_report" in ctx.results

    def test_step_name(self):
        assert ValidateStep().name == "validate"

    def test_wall_time_recorded(self, simple_project):
        step = ValidateStep()
        ctx = WorkflowContext(project=simple_project)
        ctx = step.execute(ctx)
        assert "validate" in ctx.wall_times


# ---------------------------------------------------------------------------
# WriteStep
# ---------------------------------------------------------------------------

class TestWriteStep:
    def test_writes_fds_file(self, simple_project, tmp_path):
        step = WriteStep(output_dir=str(tmp_path), filename="wf_test.fds")
        ctx = WorkflowContext(project=simple_project)
        ctx = step.execute(ctx)
        assert (tmp_path / "wf_test.fds").exists()

    def test_ctx_fds_filepath_set(self, simple_project, tmp_path):
        step = WriteStep(output_dir=str(tmp_path), filename="wf_test.fds")
        ctx = WorkflowContext(project=simple_project)
        ctx = step.execute(ctx)
        assert ctx.fds_filepath != ""
        assert "wf_test.fds" in ctx.fds_filepath

    def test_default_filename_uses_chid(self, simple_project, tmp_path):
        step = WriteStep(output_dir=str(tmp_path))
        ctx = WorkflowContext(project=simple_project)
        ctx = step.execute(ctx)
        assert (tmp_path / "wf_test.fds").exists()

    def test_creates_output_dir_if_missing(self, simple_project, tmp_path):
        new_dir = tmp_path / "subdir"
        step = WriteStep(output_dir=str(new_dir))
        ctx = WorkflowContext(project=simple_project)
        ctx = step.execute(ctx)
        assert new_dir.exists()

    def test_step_name(self):
        assert WriteStep(output_dir="/tmp").name == "write"

    def test_wall_time_recorded(self, simple_project, tmp_path):
        step = WriteStep(output_dir=str(tmp_path))
        ctx = WorkflowContext(project=simple_project)
        ctx = step.execute(ctx)
        assert "write" in ctx.wall_times


# ---------------------------------------------------------------------------
# WorkflowEngine
# ---------------------------------------------------------------------------

class TestWorkflowEngine:
    def test_empty_engine_runs_without_error(self, simple_project):
        engine = WorkflowEngine()
        ctx = engine.run(simple_project)
        assert isinstance(ctx, WorkflowContext)

    def test_steps_execute_in_order(self, simple_project):
        order = []

        class RecordStep:
            name = "RecordStep"
            def __init__(self, tag):
                self._tag = tag
            def execute(self, ctx):
                order.append(self._tag)
                return ctx

        engine = WorkflowEngine()
        engine.add_step(RecordStep("first"))
        engine.add_step(RecordStep("second"))
        engine.add_step(RecordStep("third"))
        engine.run(simple_project)
        assert order == ["first", "second", "third"]

    def test_stop_flag_halts_remaining_steps(self, simple_project):
        executed = []

        class StopStep:
            name = "Stopper"
            def execute(self, ctx):
                ctx.stop = True
                executed.append("stop")
                return ctx

        class AfterStep:
            name = "After"
            def execute(self, ctx):
                executed.append("after")
                return ctx

        engine = WorkflowEngine()
        engine.add_step(StopStep())
        engine.add_step(AfterStep())
        engine.run(simple_project)
        assert "stop" in executed
        assert "after" not in executed

    def test_add_step_returns_engine_for_chaining(self, simple_project):
        engine = WorkflowEngine()

        class NoopStep:
            name = "Noop"
            def execute(self, ctx): return ctx

        result = engine.add_step(NoopStep())
        assert result is engine

    def test_validate_then_write_pipeline(self, simple_project, tmp_path):
        engine = WorkflowEngine()
        engine.add_step(ValidateStep(abort_on_error=False))
        engine.add_step(WriteStep(output_dir=str(tmp_path), filename="pipeline.fds"))
        ctx = engine.run(simple_project)
        assert (tmp_path / "pipeline.fds").exists()
        assert ctx.stop is False

    def test_step_names(self, simple_project):
        engine = WorkflowEngine()

        class S1:
            name = "alpha"
            def execute(self, ctx): return ctx

        class S2:
            name = "beta"
            def execute(self, ctx): return ctx

        engine.add_step(S1()).add_step(S2())
        assert engine.step_names() == ["alpha", "beta"]

    def test_context_project_preserved_through_steps(self, simple_project):
        engine = WorkflowEngine()

        class CheckProject:
            name = "check"
            def __init__(self, original):
                self._orig = original
            def execute(self, ctx):
                assert ctx.project is self._orig
                return ctx

        engine.add_step(CheckProject(simple_project))
        engine.run(simple_project)

    def test_unhandled_exception_in_step_stops_pipeline(self, simple_project):
        """BaseWorkflowStep catches exceptions and sets ctx.stop=True."""

        class CrashStep(WriteStep):
            name = "crash"
            def _run(self, ctx):
                raise RuntimeError("intentional crash")

        engine = WorkflowEngine()
        engine.add_step(CrashStep(output_dir="/tmp"))
        ctx = engine.run(simple_project)
        assert ctx.stop is True
        assert len(ctx.errors) > 0
