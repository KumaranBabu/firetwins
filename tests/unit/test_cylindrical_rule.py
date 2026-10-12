"""Unit tests — CylindricalMeshRule (validation rule 24)."""
from __future__ import annotations

import pytest

from pyfds.domain.model import FdsProject, Mesh
from pyfds.validation.engine import ValidationEngine, Severity
from pyfds.validation.rules import CylindricalMeshRule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

rule = CylindricalMeshRule()


def _mesh(name="m", cylindrical=False, x_min=0.0, x_max=5.0,
          y_min=0.0, y_max=5.0, z_min=0.0, z_max=5.0):
    return Mesh(name=name,
                cylindrical=cylindrical,
                x_min=x_min, x_max=x_max,
                y_min=y_min, y_max=y_max,
                z_min=z_min, z_max=z_max,
                cell_count=(10, 10, 10))


def _project(*meshes):
    p = FdsProject()
    for m in meshes:
        p.add_entity(m)
    return p


# ---------------------------------------------------------------------------
# No cylindrical meshes
# ---------------------------------------------------------------------------

class TestNoCylindricalMeshes:
    def test_no_issues_when_no_cylindrical(self):
        p = _project(_mesh(cylindrical=False))
        assert rule.check(p) == []

    def test_no_issues_empty_project(self):
        p = FdsProject()
        assert rule.check(p) == []

    def test_no_issues_multiple_normal_meshes(self):
        p = _project(
            _mesh("a", cylindrical=False),
            _mesh("b", cylindrical=False),
        )
        assert rule.check(p) == []


# ---------------------------------------------------------------------------
# Single valid cylindrical mesh
# ---------------------------------------------------------------------------

class TestValidCylindricalMesh:
    def test_x_min_zero_no_error(self):
        p = _project(_mesh("cyl", cylindrical=True, x_min=0.0, x_max=5.0))
        results = rule.check(p)
        assert results == []

    def test_only_errors_not_warnings_for_valid(self):
        p = _project(_mesh("cyl", cylindrical=True, x_min=0.0, x_max=3.0))
        errors = [r for r in rule.check(p) if r.severity == Severity.ERROR]
        assert errors == []


# ---------------------------------------------------------------------------
# x_min != 0 error
# ---------------------------------------------------------------------------

class TestXminNonZero:
    def test_x_min_nonzero_raises_error(self):
        p = _project(_mesh("cyl", cylindrical=True, x_min=0.5, x_max=5.0))
        results = rule.check(p)
        assert len(results) == 1
        assert results[0].severity == Severity.ERROR

    def test_error_message_mentions_x_min(self):
        p = _project(_mesh("cyl", cylindrical=True, x_min=1.0, x_max=5.0))
        msg = rule.check(p)[0].message
        assert "x_min" in msg.lower() or "x_min" in msg

    def test_error_references_mesh_name(self):
        p = _project(_mesh("my_cyl", cylindrical=True, x_min=2.0, x_max=5.0))
        msg = rule.check(p)[0].message
        assert "my_cyl" in msg

    def test_negative_x_min_also_raises(self):
        # x_min < 0 is also invalid (centrepiece must be at r=0)
        p = _project(_mesh("cyl", cylindrical=True, x_min=-1.0, x_max=5.0))
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# x_max <= 0 error
# ---------------------------------------------------------------------------

class TestXmaxNonPositive:
    def test_x_max_zero_raises_error(self):
        # Mesh(x_min=0, x_max=0) would be caught by model validator first,
        # so use a slightly unusual case: provide a negative x_max is not
        # possible through normal Mesh (validator blocks x_max <= x_min).
        # Test via a direct check with a mock-like approach.
        from types import SimpleNamespace
        import pyfds.validation.rules as rules_module

        class _FakeProject:
            meshes = [SimpleNamespace(
                name="bad", cylindrical=True, x_min=0.0, x_max=-1.0
            )]

        results = rule.check(_FakeProject())
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Multiple cylindrical meshes
# ---------------------------------------------------------------------------

class TestMultipleCylindricalMeshes:
    def test_two_cylindrical_meshes_error(self):
        p = _project(
            _mesh("cyl1", cylindrical=True, x_min=0.0, x_max=5.0),
            _mesh("cyl2", cylindrical=True, x_min=0.0, x_max=3.0),
        )
        results = rule.check(p)
        errors = [r for r in results if r.severity == Severity.ERROR]
        assert len(errors) >= 1

    def test_error_message_mentions_both_names(self):
        p = _project(
            _mesh("first_cyl",  cylindrical=True, x_min=0.0, x_max=5.0),
            _mesh("second_cyl", cylindrical=True, x_min=0.0, x_max=3.0),
        )
        msg = rule.check(p)[0].message
        assert "first_cyl" in msg and "second_cyl" in msg

    def test_three_cylindrical_meshes_still_one_error(self):
        p = _project(
            _mesh("c1", cylindrical=True, x_min=0.0, x_max=5.0),
            _mesh("c2", cylindrical=True, x_min=0.0, x_max=5.0),
            _mesh("c3", cylindrical=True, x_min=0.0, x_max=5.0),
        )
        multi_errors = [r for r in rule.check(p)
                        if "Multiple" in r.message or "multiple" in r.message.lower()]
        assert len(multi_errors) == 1


# ---------------------------------------------------------------------------
# Mixed project (one cylindrical, one normal)
# ---------------------------------------------------------------------------

class TestMixedProject:
    def test_one_cyl_one_normal_valid(self):
        p = _project(
            _mesh("normal", cylindrical=False),
            _mesh("cyl",    cylindrical=True, x_min=0.0, x_max=5.0),
        )
        assert rule.check(p) == []

    def test_one_cyl_bad_xmin_one_normal(self):
        p = _project(
            _mesh("normal", cylindrical=False),
            _mesh("cyl",    cylindrical=True, x_min=1.0, x_max=5.0),
        )
        results = rule.check(p)
        assert any(r.severity == Severity.ERROR for r in results)


# ---------------------------------------------------------------------------
# x_min tolerance boundary
# ---------------------------------------------------------------------------

class TestXminTolerance:
    def test_x_min_below_1e_6_passes(self):
        # Rule uses abs(x_min) > 1e-6; values within that are OK
        p = _project(_mesh("cyl", cylindrical=True, x_min=1e-10, x_max=5.0))
        errors = [r for r in rule.check(p) if r.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_x_min_above_1e_6_fails(self):
        p = _project(_mesh("cyl", cylindrical=True, x_min=1e-5, x_max=5.0))
        errors = [r for r in rule.check(p) if r.severity == Severity.ERROR]
        assert len(errors) >= 1

    def test_error_message_contains_x_min_value(self):
        p = _project(_mesh("cyl", cylindrical=True, x_min=0.25, x_max=5.0))
        msg = rule.check(p)[0].message
        assert "0.25" in msg or "x_min" in msg.lower()


# ---------------------------------------------------------------------------
# cylindrical=None treated as non-cylindrical
# ---------------------------------------------------------------------------

class TestCylindricalNone:
    def test_cylindrical_none_not_flagged(self):
        from types import SimpleNamespace

        class _FakeProject:
            meshes = [SimpleNamespace(
                name="unknown", cylindrical=None,
                x_min=1.0, x_max=5.0,
                y_min=0.0, y_max=5.0, z_min=0.0, z_max=5.0,
            )]

        results = rule.check(_FakeProject())
        assert results == []

    def test_cylindrical_false_not_flagged_with_nonzero_xmin(self):
        # Normal (non-cylindrical) mesh with x_min != 0 is always fine
        p = _project(_mesh("norm", cylindrical=False, x_min=3.0, x_max=8.0))
        assert rule.check(p) == []


# ---------------------------------------------------------------------------
# Integration: registered in default engine
# ---------------------------------------------------------------------------

class TestRegisteredInEngine:
    def test_rule_registered(self):
        engine = ValidationEngine.default()
        names = [r.name for r in engine.rules]
        assert "CylindricalMesh" in names

    def test_engine_fires_rule_on_bad_project(self):
        engine = ValidationEngine.default()
        p = _project(
            _mesh("bad_cyl", cylindrical=True, x_min=2.0, x_max=8.0),
        )
        report = engine.validate(p)
        cyl_issues = [r for r in report.results if r.rule == "CylindricalMesh"]
        assert len(cyl_issues) >= 1

    def test_engine_no_issues_on_valid_project(self):
        engine = ValidationEngine.default()
        p = FdsProject()
        p.add_entity(_mesh("normal", cylindrical=False))
        report = engine.validate(p)
        cyl_issues = [r for r in report.results if r.rule == "CylindricalMesh"]
        assert cyl_issues == []
