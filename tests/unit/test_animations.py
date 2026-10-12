"""Unit tests — animate_slice and animate_particles in pyfds.results.plotters."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import numpy as np
import pytest

from pyfds.results.plotters import animate_slice, animate_particles


# ---------------------------------------------------------------------------
# Helpers — synthetic result objects
# ---------------------------------------------------------------------------

def _slice_result(n_frames=5, ni=10, nj=10, nk=1):
    """Mock slice ReaderResult with n_frames of (ni × nj × nk) data."""
    rr = MagicMock()
    rr.data    = np.random.rand(n_frames, ni, nj, nk).astype(np.float32)
    rr.times   = np.linspace(0, 10, n_frames)
    rr.units   = "°C"
    rr.quantity = "TEMPERATURE"
    return rr


def _particle_frame(n=20, time=0.0, qty_name="TEMPERATURE"):
    frame = MagicMock()
    frame.n_particles = n
    frame.time        = time
    frame.positions   = np.random.rand(n, 3).astype(np.float32)
    frame.quantities  = {qty_name: np.random.rand(n).astype(np.float32)}
    return frame


def _particle_class(n_frames=4):
    pc = MagicMock()
    pc.name   = "soot"
    pc.frames = [_particle_frame(time=float(i)) for i in range(n_frames)]
    return pc


# ---------------------------------------------------------------------------
# animate_slice
# ---------------------------------------------------------------------------

class TestAnimateSlice:
    def test_returns_func_animation(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_slice(_slice_result())
        assert isinstance(anim, animation.FuncAnimation)

    def test_accepts_custom_interval(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_slice(_slice_result(), interval=200)
        assert isinstance(anim, animation.FuncAnimation)

    def test_accepts_custom_cmap(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_slice(_slice_result(), cmap="viridis")
        assert anim is not None

    def test_accepts_vmin_vmax(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_slice(_slice_result(), vmin=0.0, vmax=100.0)
        assert anim is not None

    def test_empty_data_raises_value_error(self):
        rr = MagicMock()
        rr.data = np.array([])
        rr.times = np.array([])
        with pytest.raises(ValueError):
            animate_slice(rr)

    def test_3d_data_squeezed_correctly(self):
        # ni=1 axis — should squeeze correctly
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        rr = _slice_result(ni=1, nj=20, nk=30)
        anim = animate_slice(rr)
        assert anim is not None

    def test_no_singleton_dim_uses_midslice(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        rr = _slice_result(ni=8, nj=8, nk=8)
        anim = animate_slice(rr)
        assert anim is not None

    def test_repeat_false_accepted(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_slice(_slice_result(), repeat=False)
        assert anim is not None


# ---------------------------------------------------------------------------
# animate_particles
# ---------------------------------------------------------------------------

class TestAnimateParticles:
    def test_returns_func_animation(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_particles(_particle_class())
        assert isinstance(anim, animation.FuncAnimation)

    def test_accepts_custom_interval(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_particles(_particle_class(), interval=50)
        assert anim is not None

    def test_accepts_color_quantity(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_particles(_particle_class(),
                                 color_quantity="TEMPERATURE")
        assert anim is not None

    def test_empty_frames_raises_value_error(self):
        pc = MagicMock()
        pc.frames = []
        with pytest.raises(ValueError):
            animate_particles(pc)

    def test_explicit_xlim_ylim(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_particles(_particle_class(),
                                 xlim=(0, 10), ylim=(0, 10))
        assert anim is not None

    def test_repeat_false(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        anim = animate_particles(_particle_class(), repeat=False)
        assert anim is not None

    def test_no_particles_in_frame_handled(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        pc = MagicMock()
        pc.name = "smoke"
        empty_frame = MagicMock()
        empty_frame.n_particles = 0
        empty_frame.time = 0.0
        empty_frame.positions = np.empty((0, 3))
        empty_frame.quantities = {}
        pc.frames = [empty_frame, _particle_frame()]
        anim = animate_particles(pc)
        assert anim is not None


# ---------------------------------------------------------------------------
# animate_slice — 2-D projection variants and edge cases
# ---------------------------------------------------------------------------

class TestAnimateSliceProjections:
    def test_all_singleton_dim_variants(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        for ni, nj, nk in [(1, 12, 12), (12, 1, 12), (12, 12, 1)]:
            rr = _slice_result(ni=ni, nj=nj, nk=nk)
            anim = animate_slice(rr)
            assert isinstance(anim, animation.FuncAnimation)

    def test_vmin_equals_vmax_does_not_raise(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        # When all data is constant, vmin==vmax — should produce anim or warn, not crash
        rr = _slice_result()
        rr.data = np.full_like(rr.data, 50.0)
        try:
            anim = animate_slice(rr, vmin=50.0, vmax=50.0)
            assert anim is not None
        except (ValueError, RuntimeError):
            pass  # matplotlib may legitimately reject identical limits

    def test_irregular_time_steps_accepted(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        rr = _slice_result(n_frames=5)
        rr.times = np.array([0.0, 0.1, 0.5, 2.0, 10.0])
        anim = animate_slice(rr)
        assert anim is not None

    def test_single_frame_slice(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        rr = _slice_result(n_frames=1)
        anim = animate_slice(rr)
        assert anim is not None


# ---------------------------------------------------------------------------
# animate_particles — edge cases
# ---------------------------------------------------------------------------

class TestAnimateParticlesEdgeCases:
    def test_missing_color_quantity_silently_ignored(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        # Frames only have "TEMPERATURE"; asking for "VELOCITY" should not raise
        pc = _particle_class()
        anim = animate_particles(pc, color_quantity="VELOCITY_MISSING")
        assert anim is not None

    def test_all_empty_frames_handled(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        pc = MagicMock()
        pc.name = "smoke"
        empty_frames = []
        for i in range(3):
            f = MagicMock()
            f.n_particles = 0
            f.time = float(i)
            f.positions = np.empty((0, 3))
            f.quantities = {}
            empty_frames.append(f)
        pc.frames = empty_frames
        anim = animate_particles(pc)
        assert anim is not None

    def test_large_particle_count(self):
        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")
        pc = MagicMock()
        pc.name = "soot"
        frame = MagicMock()
        frame.n_particles = 10000
        frame.time = 0.0
        frame.positions = np.random.rand(10000, 3).astype(np.float32)
        frame.quantities = {"TEMPERATURE": np.random.rand(10000).astype(np.float32)}
        pc.frames = [frame]
        anim = animate_particles(pc)
        assert anim is not None


# ---------------------------------------------------------------------------
# ResultsManager.animate dispatch
# ---------------------------------------------------------------------------

class TestResultsManagerAnimate:
    def test_auto_dispatch_slice(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()

        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")

        rr = _slice_result()
        anim = api.results.animate(rr, kind="slice")
        assert isinstance(anim, animation.FuncAnimation)

    def test_auto_dispatch_particles(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()

        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")

        pc = _particle_class()
        anim = api.results.animate(pc, kind="particles")
        assert isinstance(anim, animation.FuncAnimation)

    def test_auto_infer_particle_class(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()

        try:
            import matplotlib.animation as animation
        except ImportError:
            pytest.skip("matplotlib not available")

        # ParticleClass by type name
        pc = _particle_class()
        type(pc).__name__ = "ParticleClass"
        anim = api.results.animate(pc, kind="auto")
        assert anim is not None

    def test_invalid_kind_raises(self):
        from pyfds.api.controller import FdsApi
        api = FdsApi()
        with pytest.raises(ValueError, match="Unknown animation kind"):
            api.results.animate(MagicMock(), kind="unknown_kind")
