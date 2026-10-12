"""Unit tests — pyfds.domain.presets (PresetEngine, ScenarioTemplate, list_presets)."""
from __future__ import annotations

import pytest
from pyfds.domain.presets import PresetEngine, ScenarioTemplate, list_presets, apply_preset
from pyfds.domain.model import FdsProject


# ---------------------------------------------------------------------------
# ScenarioTemplate
# ---------------------------------------------------------------------------

class TestScenarioTemplate:
    def test_apply_calls_builder(self):
        called_with = {}
        def builder(**kwargs):
            called_with.update(kwargs)
            return FdsProject()
        t = ScenarioTemplate(
            name="test", description="desc", tags=[],
            defaults={"x": 1},
            builder=builder,
        )
        t.apply()
        assert called_with["x"] == 1

    def test_apply_kwargs_override_defaults(self):
        received = {}
        def builder(**kwargs):
            received.update(kwargs)
            return FdsProject()
        t = ScenarioTemplate(
            name="test", description="desc", tags=[],
            defaults={"x": 1, "y": 2},
            builder=builder,
        )
        t.apply(x=99)
        assert received["x"] == 99
        assert received["y"] == 2

    def test_apply_returns_fds_project(self):
        t = ScenarioTemplate(
            name="blank", description="", tags=[],
            defaults={},
            builder=lambda **kw: FdsProject(),
        )
        result = t.apply()
        assert isinstance(result, FdsProject)


# ---------------------------------------------------------------------------
# PresetEngine — registration
# ---------------------------------------------------------------------------

class TestPresetEngineRegistration:
    def test_register_decorator(self):
        eng = PresetEngine.__new__(PresetEngine)
        eng._registry = {}
        @eng.register("my_preset", description="A custom preset", tags=["test"])
        def builder(**kwargs):
            return FdsProject()
        assert "my_preset" in eng._registry

    def test_add_template(self):
        eng = PresetEngine()
        t = ScenarioTemplate(
            name="custom", description="", tags=[],
            defaults={},
            builder=lambda **kw: FdsProject(),
        )
        eng.add(t)
        assert eng.get("custom") is t

    def test_get_nonexistent_returns_none(self):
        eng = PresetEngine()
        assert eng.get("does_not_exist") is None

    def test_names_sorted(self):
        eng = PresetEngine()
        names = eng.names()
        assert names == sorted(names)

    def test_all_templates_returns_list(self):
        eng = PresetEngine()
        templates = eng.all_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0


# ---------------------------------------------------------------------------
# PresetEngine — apply
# ---------------------------------------------------------------------------

class TestPresetEngineApply:
    def test_apply_unknown_raises_key_error(self):
        eng = PresetEngine()
        with pytest.raises(KeyError, match="no_such_preset"):
            eng.apply("no_such_preset")

    def test_apply_returns_fds_project(self):
        eng = PresetEngine()
        result = eng.apply("blank")
        assert isinstance(result, FdsProject)

    def test_apply_blank_sets_chid(self):
        eng = PresetEngine()
        proj = eng.apply("blank", chid="my_blank")
        assert proj.chid == "my_blank"

    def test_apply_blank_sets_t_end(self):
        eng = PresetEngine()
        proj = eng.apply("blank", t_end=300.0)
        assert proj.params.t_end == 300.0


# ---------------------------------------------------------------------------
# Built-in presets
# ---------------------------------------------------------------------------

class TestBuiltinPresets:
    def test_room_fire_exists(self):
        eng = PresetEngine()
        assert eng.get("room_fire") is not None

    def test_corridor_smoke_exists(self):
        eng = PresetEngine()
        assert eng.get("corridor_smoke") is not None

    def test_pool_fire_exists(self):
        eng = PresetEngine()
        assert eng.get("pool_fire") is not None

    def test_atrium_smoke_exists(self):
        eng = PresetEngine()
        assert eng.get("atrium_smoke") is not None

    def test_wildland_fire_exists(self):
        eng = PresetEngine()
        assert eng.get("wildland_fire") is not None

    def test_blank_exists(self):
        eng = PresetEngine()
        assert eng.get("blank") is not None

    def test_room_fire_has_mesh(self):
        eng = PresetEngine()
        proj = eng.apply("room_fire")
        assert len(proj.meshes) >= 1

    def test_room_fire_has_devices(self):
        eng = PresetEngine()
        proj = eng.apply("room_fire")
        assert len(proj.devices) >= 1

    def test_room_fire_has_reaction(self):
        eng = PresetEngine()
        proj = eng.apply("room_fire")
        assert len(proj.reactions) >= 1

    def test_room_fire_custom_hrr(self):
        eng = PresetEngine()
        proj = eng.apply("room_fire", hrr_kw=1000.0, t_end=120.0)
        assert proj.params.t_end == 120.0

    def test_pool_fire_has_mesh(self):
        eng = PresetEngine()
        proj = eng.apply("pool_fire")
        assert len(proj.meshes) >= 1

    def test_corridor_smoke_has_slices(self):
        eng = PresetEngine()
        proj = eng.apply("corridor_smoke")
        assert len(proj.slices) >= 1

    def test_atrium_smoke_t_end(self):
        eng = PresetEngine()
        proj = eng.apply("atrium_smoke")
        assert proj.params.t_end == 180.0

    def test_wildland_fire_has_wind_set(self):
        eng = PresetEngine()
        proj = eng.apply("wildland_fire", wind_speed=10.0)
        assert proj.misc.u0 == 10.0


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

class TestModuleHelpers:
    def test_list_presets_returns_strings(self):
        names = list_presets()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_list_presets_contains_room_fire(self):
        assert "room_fire" in list_presets()

    def test_apply_preset_blank(self):
        proj = apply_preset("blank", chid="test")
        assert isinstance(proj, FdsProject)
        assert proj.chid == "test"

    def test_apply_preset_unknown_raises(self):
        with pytest.raises(KeyError):
            apply_preset("nonexistent_preset")
