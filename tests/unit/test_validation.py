"""Unit tests — pyfds.validation (engine + built-in rules)."""
from __future__ import annotations

import pytest
from pyfds.domain.model import (
    FdsProject, Mesh, Surface, Obstruction, Vent, Device,
    HvacNode, HvacDuct, Ramp,
)
from pyfds.validation.engine import (
    ValidationEngine, ValidationReport, ValidationResult, Severity,
)
from pyfds.validation.rules import (
    PoissonComplianceRule, MpiRankGapRule, MeshAlignmentRule,
    RampMonotonicityRule, ObstBoundsRule,
)


def _make_mesh(name="m1", nx=16, ny=16, nz=8,
               x_min=0, x_max=4, y_min=0, y_max=4, z_min=0, z_max=2):
    """Helper: create a Mesh with the actual domain model fields."""
    return Mesh(name=name, cell_count=(nx, ny, nz),
                x_min=x_min, x_max=x_max,
                y_min=y_min, y_max=y_max,
                z_min=z_min, z_max=z_max)


def _make_project_with_mesh(mesh_name="m1", **mesh_kwargs):
    p = FdsProject()
    p.add_entity(_make_mesh(mesh_name, **mesh_kwargs))
    return p


# ---------------------------------------------------------------------------
# ValidationResult / ValidationReport
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_str_error(self):
        r = ValidationResult(Severity.ERROR, "MyRule", "mesh missing")
        assert "[ERROR]" in str(r)
        assert "mesh missing" in str(r)

    def test_str_warning(self):
        r = ValidationResult(Severity.WARNING, "R", "low resolution")
        assert "[WARN]" in str(r)

    def test_str_with_entity_name(self):
        r = ValidationResult(Severity.INFO, "R", "ok", entity_name="mesh_01")
        assert "mesh_01" in str(r)


class TestValidationReport:
    def _make_report(self):
        return ValidationReport(project_chid="test", elapsed_seconds=0.01)

    def test_empty_report(self):
        r = self._make_report()
        assert r.errors == []
        assert r.warnings == []
        assert r.infos == []

    def test_errors_filtered(self):
        r = self._make_report()
        r.results.append(ValidationResult(Severity.ERROR, "R", "e1"))
        r.results.append(ValidationResult(Severity.WARNING, "R", "w1"))
        assert len(r.errors) == 1
        assert len(r.warnings) == 1

    def test_passed_property_true_when_no_errors(self):
        r = self._make_report()
        r.results.append(ValidationResult(Severity.WARNING, "R", "w"))
        assert r.passed is True

    def test_passed_property_false_when_errors(self):
        r = self._make_report()
        r.results.append(ValidationResult(Severity.ERROR, "R", "e"))
        assert r.passed is False


# ---------------------------------------------------------------------------
# ValidationEngine
# ---------------------------------------------------------------------------

class TestValidationEngine:
    def test_default_engine_has_rules(self):
        engine = ValidationEngine.default()
        assert len(engine.rules) > 0

    def test_empty_engine_validates_without_crash(self):
        engine = ValidationEngine()
        p = _make_project_with_mesh()
        report = engine.validate(p)
        assert isinstance(report, ValidationReport)

    def test_validate_project_with_no_mesh_produces_error(self):
        engine = ValidationEngine.default()
        p = FdsProject()
        report = engine.validate(p)
        # No mesh = critical error
        assert not report.passed

    def test_validate_clean_project_passes(self):
        engine = ValidationEngine.default()
        p = _make_project_with_mesh(nx=16, ny=16, nz=8)
        p.add_entity(Surface(name="inert"))
        report = engine.validate(p)
        assert report.passed

    def test_add_custom_rule(self):
        engine = ValidationEngine()

        class AlwaysError:
            name = "AlwaysError"
            def check(self, project):
                return [ValidationResult(Severity.ERROR, "AlwaysError", "forced")]

        engine.add_rule(AlwaysError())
        p = _make_project_with_mesh()
        report = engine.validate(p)
        assert not report.passed

    def test_remove_rule(self):
        engine = ValidationEngine.default()
        n_before = len(engine.rules)
        engine.remove_rule("PoissonCompliance")
        assert len(engine.rules) == n_before - 1

    def test_report_contains_project_chid(self):
        engine = ValidationEngine()
        p = FdsProject()
        p.chid = "my_chid"
        p.add_entity(_make_mesh())
        report = engine.validate(p)
        assert report.project_chid == "my_chid"

    def test_report_elapsed_seconds_non_negative(self):
        engine = ValidationEngine.default()
        p = _make_project_with_mesh()
        report = engine.validate(p)
        assert report.elapsed_seconds >= 0


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------

class TestPoissonComplianceRule:
    def test_compliant_mesh_no_error(self):
        rule = PoissonComplianceRule()
        p = _make_project_with_mesh(nx=16, ny=16, nz=8)
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert errors == []

    def test_non_compliant_mesh_produces_error(self):
        rule = PoissonComplianceRule()
        p = _make_project_with_mesh(nx=7, ny=11, nz=13)
        results = rule.check(p)
        assert len(results) > 0

    def test_compliant_mixed_factors(self):
        rule = PoissonComplianceRule()
        p = _make_project_with_mesh(nx=12, ny=40, nz=18)  # all 2^a*3^b*5^c
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert errors == []


class TestMpiRankGapRule:
    def test_single_mesh_no_gap(self):
        rule = MpiRankGapRule()
        p = _make_project_with_mesh()
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert errors == []

    def test_continuous_ranks_no_gap(self):
        rule = MpiRankGapRule()
        p = FdsProject()
        m1 = Mesh(name="m1", cell_count=(10, 10, 5), mpi_processor=0,
                  x_min=0, x_max=2, y_min=0, y_max=2, z_min=0, z_max=1)
        m2 = Mesh(name="m2", cell_count=(10, 10, 5), mpi_processor=1,
                  x_min=2, x_max=4, y_min=0, y_max=2, z_min=0, z_max=1)
        p.add_entity(m1); p.add_entity(m2)
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert errors == []

    def test_rank_gap_produces_error(self):
        rule = MpiRankGapRule()
        p = FdsProject()
        m1 = Mesh(name="m1", cell_count=(10, 10, 5), mpi_processor=0,
                  x_min=0, x_max=2, y_min=0, y_max=2, z_min=0, z_max=1)
        m2 = Mesh(name="m2", cell_count=(10, 10, 5), mpi_processor=2,  # skips rank 1
                  x_min=2, x_max=4, y_min=0, y_max=2, z_min=0, z_max=1)
        p.add_entity(m1); p.add_entity(m2)
        results = rule.check(p)
        assert len(results) > 0


class TestRampMonotonicityRule:
    def test_monotonic_ramp_passes(self):
        rule = RampMonotonicityRule()
        p = _make_project_with_mesh()
        # Ramp model enforces monotonicity at construction time, so valid ramp:
        ramp = Ramp(name="r", times=[0.0, 10.0, 30.0], values=[0.0, 0.5, 1.0])
        p.add_entity(ramp)
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert errors == []

    def test_empty_ramp_no_issues(self):
        rule = RampMonotonicityRule()
        p = _make_project_with_mesh()
        ramp = Ramp(name="empty")
        p.add_entity(ramp)
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert errors == []


class TestObstBoundsRule:
    def test_obst_inside_mesh_passes(self):
        rule = ObstBoundsRule()
        p = FdsProject()
        p.add_entity(_make_mesh("m", 20, 20, 10, 0, 4, 0, 4, 0, 2))
        p.add_entity(Obstruction(name="o",
                                 x_min=1, x_max=2, y_min=1, y_max=2,
                                 z_min=0, z_max=0.5, surface_id="INERT"))
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert errors == []

    def test_obst_outside_all_meshes_error(self):
        rule = ObstBoundsRule()
        p = FdsProject()
        p.add_entity(_make_mesh("m", 10, 10, 5, 0, 2, 0, 2, 0, 1))
        p.add_entity(Obstruction(name="floating",
                                 x_min=5, x_max=6, y_min=5, y_max=6,
                                 z_min=5, z_max=6, surface_id="INERT"))
        results = rule.check(p)
        assert len(results) > 0
