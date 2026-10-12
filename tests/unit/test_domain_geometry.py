"""Unit tests — pyfds.domain.geometry (BoundingBox, GeometryHelper)."""
from __future__ import annotations

import math
import pytest
from pyfds.domain.geometry import BoundingBox, GeometryHelper


class TestBoundingBox:
    def test_from_xb_basic(self):
        bb = BoundingBox.from_xb([0, 4, 0, 4, 0, 2])
        assert bb.x_min == 0 and bb.x_max == 4
        assert bb.y_min == 0 and bb.y_max == 4
        assert bb.z_min == 0 and bb.z_max == 2

    def test_from_xb_wrong_length(self):
        with pytest.raises(ValueError):
            BoundingBox.from_xb([0, 1, 2, 3])

    def test_dx_dy_dz(self):
        bb = BoundingBox(0, 3, 0, 4, 0, 2)
        assert bb.dx == 3
        assert bb.dy == 4
        assert bb.dz == 2

    def test_volume(self):
        bb = BoundingBox(0, 2, 0, 3, 0, 4)
        assert bb.volume == 24.0

    def test_surface_area(self):
        bb = BoundingBox(0, 1, 0, 1, 0, 1)
        assert bb.surface_area == 6.0

    def test_center(self):
        bb = BoundingBox(0, 4, 0, 4, 0, 2)
        cx, cy, cz = bb.center
        assert cx == 2.0
        assert cy == 2.0
        assert cz == 1.0

    def test_xb_property_round_trips(self):
        xb_in = [1.0, 3.0, 2.0, 5.0, 0.5, 2.5]
        bb = BoundingBox.from_xb(xb_in)
        assert bb.xb == xb_in

    def test_overlaps_true(self):
        a = BoundingBox(0, 2, 0, 2, 0, 2)
        b = BoundingBox(1, 3, 1, 3, 1, 3)
        assert a.overlaps(b)

    def test_overlaps_false_no_overlap(self):
        a = BoundingBox(0, 1, 0, 1, 0, 1)
        b = BoundingBox(2, 3, 2, 3, 2, 3)
        assert not a.overlaps(b)

    def test_contains_point_inside(self):
        bb = BoundingBox(0, 4, 0, 4, 0, 2)
        assert bb.contains_point(2.0, 2.0, 1.0)

    def test_contains_point_outside(self):
        bb = BoundingBox(0, 4, 0, 4, 0, 2)
        assert not bb.contains_point(5.0, 2.0, 1.0)

    def test_union(self):
        a = BoundingBox(0, 2, 0, 2, 0, 2)
        b = BoundingBox(1, 4, 1, 4, 1, 4)
        u = a.union(b)
        assert u.x_min == 0 and u.x_max == 4
        assert u.y_min == 0 and u.y_max == 4
        assert u.z_min == 0 and u.z_max == 4

    def test_expand(self):
        bb = BoundingBox(1, 3, 1, 3, 1, 3)
        expanded = bb.expand(1.0, 1.0, 1.0)
        assert expanded.x_min == 0
        assert expanded.x_max == 4

    def test_intersection_overlap(self):
        a = BoundingBox(0, 2, 0, 2, 0, 2)
        b = BoundingBox(1, 3, 1, 3, 1, 3)
        inter = a.intersection(b)
        assert inter is not None
        assert inter.x_min == 1 and inter.x_max == 2

    def test_intersection_no_overlap_returns_none(self):
        a = BoundingBox(0, 1, 0, 1, 0, 1)
        b = BoundingBox(2, 3, 2, 3, 2, 3)
        assert a.intersection(b) is None

    def test_zero_volume(self):
        bb = BoundingBox(1, 1, 0, 2, 0, 2)
        assert bb.volume == 0.0

    def test_from_entity(self):
        class FakeEntity:
            x_min = 0.0; x_max = 2.0
            y_min = 0.0; y_max = 1.0
            z_min = 0.0; z_max = 0.5
        bb = BoundingBox.from_entity(FakeEntity())
        assert bb.dx == 2.0

    def test_abuts_returns_axis(self):
        a = BoundingBox(0, 2, 0, 2, 0, 2)
        b = BoundingBox(2, 4, 0, 2, 0, 2)
        axis = a.abuts(b)
        assert axis == "X"

    def test_abuts_non_touching_returns_none(self):
        a = BoundingBox(0, 1, 0, 1, 0, 1)
        b = BoundingBox(3, 4, 0, 1, 0, 1)
        assert a.abuts(b) is None

    def test_contains_box_true(self):
        outer = BoundingBox(0, 10, 0, 10, 0, 10)
        inner = BoundingBox(1, 9, 1, 9, 1, 9)
        assert outer.contains_box(inner)

    def test_contains_box_false(self):
        a = BoundingBox(0, 1, 0, 1, 0, 1)
        b = BoundingBox(0, 2, 0, 2, 0, 2)
        assert not a.contains_box(b)


class TestGeometryHelper:
    # ── Poisson compliance ────────────────────────────────────────────────────

    def test_poisson_compliant_powers_of_2(self):
        assert GeometryHelper.is_poisson_compliant(64)
        assert GeometryHelper.is_poisson_compliant(32)
        assert GeometryHelper.is_poisson_compliant(16)

    def test_poisson_compliant_mixed(self):
        # 2^2 * 3 = 12
        assert GeometryHelper.is_poisson_compliant(12)
        # 2^3 * 5 = 40
        assert GeometryHelper.is_poisson_compliant(40)

    def test_poisson_non_compliant(self):
        assert not GeometryHelper.is_poisson_compliant(7)
        assert not GeometryHelper.is_poisson_compliant(11)

    def test_poisson_compliant_1(self):
        assert GeometryHelper.is_poisson_compliant(1)

    def test_poisson_non_compliant_zero(self):
        assert not GeometryHelper.is_poisson_compliant(0)

    def test_nearest_poisson_already_compliant(self):
        assert GeometryHelper.nearest_poisson(16) == 16

    def test_nearest_poisson_rounds_up(self):
        n = GeometryHelper.nearest_poisson(7)
        assert n >= 7
        assert GeometryHelper.is_poisson_compliant(n)

    # ── Cell sizes ─────────────────────────────────────────────────────────────

    def test_cell_sizes(self):
        box = BoundingBox(0, 2, 0, 2, 0, 1)
        dx, dy, dz = GeometryHelper.cell_sizes(box, (20, 20, 10))
        assert abs(dx - 0.1) < 1e-9
        assert abs(dy - 0.1) < 1e-9
        assert abs(dz - 0.1) < 1e-9

    def test_auto_cell_count_poisson(self):
        box = BoundingBox(0, 4, 0, 4, 0, 2)
        nx, ny, nz = GeometryHelper.auto_cell_count(box, dx=0.2, force_poisson=True)
        assert GeometryHelper.is_poisson_compliant(nx)
        assert GeometryHelper.is_poisson_compliant(ny)
        assert GeometryHelper.is_poisson_compliant(nz)

    def test_auto_cell_count_no_poisson(self):
        box = BoundingBox(0, 4, 0, 4, 0, 2)
        nx, ny, nz = GeometryHelper.auto_cell_count(box, dx=0.2, force_poisson=False)
        assert nx == 20

    # ── D* fire resolution ────────────────────────────────────────────────────

    def test_fire_diameter_positive(self):
        d_star = GeometryHelper.fire_diameter(hrr_kw=100.0)
        assert d_star > 0

    def test_fire_diameter_scales_with_hrr(self):
        d1 = GeometryHelper.fire_diameter(100.0)
        d2 = GeometryHelper.fire_diameter(1000.0)
        assert d2 > d1

    def test_recommended_cell_size(self):
        cs = GeometryHelper.recommended_cell_size(hrr_kw=1000.0, ratio=10.0)
        d_star = GeometryHelper.fire_diameter(1000.0)
        assert abs(cs - d_star / 10.0) < 1e-9

    def test_dstar_dx_ratio(self):
        ratio = GeometryHelper.dstar_dx_ratio(hrr_kw=500.0, dx=0.05)
        assert ratio > 0

    # ── Domain splitting ──────────────────────────────────────────────────────

    def test_split_x_count(self):
        box = BoundingBox(0, 4, 0, 2, 0, 2)
        slabs = GeometryHelper.split_x(box, 4)
        assert len(slabs) == 4

    def test_split_x_no_gaps(self):
        box = BoundingBox(0, 4, 0, 2, 0, 2)
        slabs = GeometryHelper.split_x(box, 4)
        assert abs(slabs[0].x_min - 0.0) < 1e-9
        assert abs(slabs[-1].x_max - 4.0) < 1e-9

    def test_split_y_count(self):
        box = BoundingBox(0, 4, 0, 6, 0, 2)
        slabs = GeometryHelper.split_y(box, 3)
        assert len(slabs) == 3

    def test_split_z_count(self):
        box = BoundingBox(0, 4, 0, 4, 0, 2)
        slabs = GeometryHelper.split_z(box, 2)
        assert len(slabs) == 2

    # ── Poisson factors ───────────────────────────────────────────────────────

    def test_poisson_factors_pure_power_of_2(self):
        factors = GeometryHelper.poisson_factors(8)
        assert set(factors) == {2}

    def test_poisson_factors_non_compliant(self):
        factors = GeometryHelper.poisson_factors(7)
        assert 7 in factors  # non-Poisson factor remains
