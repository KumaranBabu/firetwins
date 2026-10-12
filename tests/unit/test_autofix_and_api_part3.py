"""Tests for: (part 1 of 1). (part 3 of 3)."""


from __future__ import annotations

import pytest

from pyfds.domain.model import (
    FdsProject, Mesh, Obstruction, Surface, Vent, Device, Prop,
    Ramp, Material, Reaction, HvacNode, HvacDuct, Control,
    Layer, Species,
)
from pyfds.validation.engine import ValidationEngine, Severity
from pyfds.validation.rules import (
    MeshPresenceRule, MeshAlignmentRule, HvacNodeReferenceRule,
    ReferenceIntegrityRule, FireResolutionRule, HvacTopologyRule,
    DuplicateIdRule, VentCoplanarRule, SurfaceLayerRule,
    FuelSpeciesRule, BackingValueRule, MeshAspectRatioRule,
)


class TestApiOptimizeForFire:

    def test_returns_dict(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.project.meshes.append(Mesh(
            name="M1", x_min=0, x_max=10, y_min=0, y_max=10,
            z_min=0, z_max=4, cell_count=(40, 40, 16),
        ))
        api.project.surfaces.append(Surface(name="FIRE", heat_release_rate=500.0))
        result = api.optimize_for_fire("FIRE", fire_area=2.0)
        assert isinstance(result, dict)
        assert "D_star_m" in result

    def test_matches_meshing_manager_result(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        api.project.meshes.append(Mesh(
            name="M1", x_min=0, x_max=10, y_min=0, y_max=10,
            z_min=0, z_max=4, cell_count=(40, 40, 16),
        ))
        api.project.surfaces.append(Surface(name="FIRE", heat_release_rate=500.0))
        r1 = api.optimize_for_fire("FIRE", fire_area=1.0)
        r2 = api.meshing.optimize_for_fire(api.project, "FIRE", fire_area=1.0)
        assert r1["D_star_m"] == r2["D_star_m"]

class TestResultsManagerCompare:

    def test_compare_returns_report(self, tmp_path):
        from pyfds.api.controller import FdsApi
        from pyfds.results.comparator import ComparisonReport
        d1 = tmp_path / "dir1"
        d2 = tmp_path / "dir2"
        d1.mkdir(); d2.mkdir()
        api = FdsApi()
        report = api.results.compare(str(d1), str(d2), threshold_pct=5.0)
        assert isinstance(report, ComparisonReport)
        assert report.threshold_pct == 5.0

    def test_compare_empty_dirs_passes(self, tmp_path):
        from pyfds.api.controller import FdsApi
        d1 = tmp_path / "a"; d2 = tmp_path / "b"
        d1.mkdir(); d2.mkdir()
        report = FdsApi().results.compare(str(d1), str(d2))
        assert report.passed

class TestRunBatch:

    def test_run_batch_exists(self):
        from pyfds.api.controller import FdsApi, ExecutionManager
        assert hasattr(ExecutionManager, "run_batch")

    def test_run_batch_callable(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        assert callable(api.execution.run_batch)
