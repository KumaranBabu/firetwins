"""
Tests for pyfds.engineering.mesh_advisor — D*, Q*, cell-size, MPI decomposition.
"""
from __future__ import annotations

import math
import pytest

from pyfds.engineering.mesh_advisor import (
    d_star, q_star, recommend_cell_size, MeshAdvice,
    poisson_ijk_for_domain, actual_cell_size, mpi_split_advice,
    _next_poisson, G, RHO, CP, T_0,
)


class TestDStar:
    def test_positive_output(self):
        assert d_star(1000.0) > 0.0

    def test_scales_as_two_fifths(self):
        # D*(2Q) = 2^(2/5) × D*(Q)
        d1 = d_star(1000.0)
        d2 = d_star(2000.0)
        assert d2 == pytest.approx(d1 * 2.0 ** 0.4, rel=1e-5)

    def test_formula(self):
        q = 500.0
        expected = (q / (RHO * CP * T_0 * math.sqrt(G))) ** 0.4
        assert d_star(q) == pytest.approx(expected, rel=1e-6)

    def test_1mw_fire_reasonable_magnitude(self):
        # D* for 1 MW fire with standard air (ρ=1.204, T₀=293 K) ≈ 0.96 m
        ds = d_star(1000.0)
        assert 0.5 < ds < 2.0

    def test_100kw_fire_smaller_than_1mw(self):
        assert d_star(100.0) < d_star(1000.0)


class TestQStar:
    def test_zero_D_raises(self):
        with pytest.raises(ValueError):
            q_star(1000.0, D=0.0)

    def test_negative_D_raises(self):
        with pytest.raises(ValueError):
            q_star(1000.0, D=-1.0)

    def test_positive_output(self):
        assert q_star(1000.0, D=1.0) > 0.0

    def test_scales_linearly_with_q(self):
        q1 = q_star(500.0, D=1.0)
        q2 = q_star(1000.0, D=1.0)
        assert q2 == pytest.approx(2.0 * q1, rel=1e-6)

    def test_large_fire_large_qstar(self):
        assert q_star(10000.0, D=0.5) > 1.0   # large fire in small pool → Q* >> 1

    def test_formula(self):
        q, D = 1000.0, 1.0
        expected = q / (RHO * CP * T_0 * math.sqrt(G) * D ** 2.5)
        assert q_star(q, D) == pytest.approx(expected, rel=1e-6)


class TestRecommendCellSize:
    def test_returns_mesh_advice(self):
        advice = recommend_cell_size(1000.0)
        assert isinstance(advice, MeshAdvice)

    def test_dx_max_is_d_star_over_10(self):
        advice = recommend_cell_size(1000.0, ratio_min=10.0)
        assert advice.dx_max_m == pytest.approx(d_star(1000.0) / 10.0, rel=1e-6)

    def test_dx_recommended_is_d_star_over_15(self):
        advice = recommend_cell_size(1000.0, ratio_target=15.0)
        assert advice.dx_recommended_m == pytest.approx(d_star(1000.0) / 15.0, rel=1e-6)

    def test_dx_well_resolved_is_d_star_over_20(self):
        advice = recommend_cell_size(1000.0, ratio_max=20.0)
        assert advice.dx_well_resolved_m == pytest.approx(d_star(1000.0) / 20.0, rel=1e-6)

    def test_cell_size_ordering(self):
        advice = recommend_cell_size(2000.0)
        assert advice.dx_well_resolved_m < advice.dx_recommended_m < advice.dx_max_m

    def test_1mw_fire_typical_cell_size(self):
        advice = recommend_cell_size(1000.0)
        # For ~1 MW fire, recommended cell size should be around 0.1–0.2 m
        assert 0.05 < advice.dx_recommended_m < 0.5

    def test_higher_hrr_allows_coarser_mesh(self):
        a1 = recommend_cell_size(500.0)
        a2 = recommend_cell_size(5000.0)
        assert a2.dx_recommended_m > a1.dx_recommended_m


class TestPoissonIJK:
    def test_unit_domain_unit_cell(self):
        nx, ny, nz = poisson_ijk_for_domain(1.0, 1.0, 1.0, dx=1.0)
        assert nx == ny == nz == 1

    def test_result_is_poisson_compliant(self):
        for n in poisson_ijk_for_domain(5.3, 3.7, 2.1, dx=0.25):
            # n must be expressible as 2^a × 3^b × 5^c × 7^d
            m = n
            for p in (2, 3, 5, 7):
                while m % p == 0:
                    m //= p
            assert m == 1, f"{n} is not Poisson-compliant"

    def test_cells_cover_domain(self):
        lx, ly, lz, dx = 10.0, 8.0, 4.0, 0.5
        nx, ny, nz = poisson_ijk_for_domain(lx, ly, lz, dx)
        assert nx * dx >= lx
        assert ny * dx >= ly
        assert nz * dx >= lz

    def test_non_uniform_domain(self):
        nx, ny, nz = poisson_ijk_for_domain(20.0, 10.0, 5.0, dx=0.5)
        assert nx >= 40
        assert ny >= 20
        assert nz >= 10


class TestNextPoisson:
    def test_powers_of_two(self):
        for exp in range(1, 10):
            assert _next_poisson(2 ** exp) == 2 ** exp

    def test_prime_7_compliant(self):
        assert _next_poisson(7) == 7

    def test_prime_11_not_compliant(self):
        n = _next_poisson(11)
        assert n > 11 or n == 12   # next after 11 is 12 (2²×3)

    def test_always_ge_input(self):
        for n in range(1, 50):
            assert _next_poisson(n) >= n


class TestActualCellSize:
    def test_basic(self):
        assert actual_cell_size(10.0, 20) == pytest.approx(0.5)

    def test_non_integer_result(self):
        assert actual_cell_size(7.0, 14) == pytest.approx(0.5)


class TestMpiSplitAdvice:
    def test_correct_number_of_meshes(self):
        advice = mpi_split_advice(20.0, 10.0, 5.0, dx=0.5, n_ranks=4)
        assert len(advice.meshes) == 4

    def test_domain_covered(self):
        lx = 20.0
        advice = mpi_split_advice(lx, 10.0, 5.0, dx=0.5, n_ranks=4, split_axis="X")
        assert advice.meshes[0][0] == pytest.approx(0.0, abs=1e-6)
        assert advice.meshes[-1][1] == pytest.approx(lx, abs=1e-6)

    def test_auto_chooses_longest_axis(self):
        advice = mpi_split_advice(30.0, 10.0, 5.0, dx=0.5, n_ranks=4, split_axis="auto")
        assert advice.split_axis == "X"

    def test_explicit_y_split(self):
        advice = mpi_split_advice(10.0, 30.0, 5.0, dx=0.5, n_ranks=3, split_axis="Y")
        assert advice.split_axis == "Y"

    def test_total_cells_positive(self):
        advice = mpi_split_advice(20.0, 10.0, 5.0, dx=0.5, n_ranks=4)
        assert advice.total_cells > 0
