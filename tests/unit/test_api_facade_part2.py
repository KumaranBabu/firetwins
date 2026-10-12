"""Unit tests — pyfds.api.controller (FdsApi facade). (part 2 of 2)."""


from __future__ import annotations

import pytest
from pyfds.api.controller import FdsApi
from pyfds.domain.model import (
    FdsProject, Mesh, Surface, Obstruction, Device, Ramp, Vent, Material,
)


@pytest.fixture
def api():
    """FdsApi instance with a blank project."""
    return FdsApi()


class TestMaterialManager:
    def test_add_from_library_returns_populated_material(self, api):
        # Regression: add_from_library instantiated a fresh, empty
        # domain.materials.MaterialLibrary() (a legacy v0.2 shim) instead of
        # the populated domain.material_presets registry — every preset
        # name, including real ones, always raised KeyError.
        m = api.materials.add_from_library("concrete")
        assert isinstance(m, Material)
        assert m.density == pytest.approx(2280.0)
        assert m.conductivity == pytest.approx(1.6)

    def test_add_from_library_unknown_preset_raises(self, api):
        with pytest.raises(KeyError):
            api.materials.add_from_library("not_a_real_material")

class TestDeviceManager:
    def test_add_thermocouple(self, api):
        d = api.devices.add_thermocouple(xyz=(1.0, 1.0, 1.5), devc_id="tc01")
        assert isinstance(d, Device)
        assert d.quantity == "TEMPERATURE"

    def test_add_thermocouple_sets_name_from_devc_id(self, api):
        # Regression: Device.id is a read-only alias for .name (FdsEntity), so
        # constructing with id= instead of name= silently drops it via
        # pydantic's extra="allow" and every device ends up "DefaultDevice".
        d = api.devices.add_thermocouple(xyz=(1, 1, 1), devc_id="tc01")
        assert d.name == "tc01"
        assert api.devices.get("tc01") is d

    def test_add_sprinkler_sets_name_from_id(self, api):
        d = api.devices.add_sprinkler(xyz=(1, 1, 2), prop_id="SPRINKLER_PROP", id="spk01")
        assert d.name == "spk01"
        assert api.devices.get("spk01") is d

    def test_all_devices(self, api):
        api.devices.add_thermocouple((1, 1, 1), "tc_a")
        api.devices.add_thermocouple((2, 2, 2), "tc_b")
        assert api.devices.count() == 2
        assert api.devices.get("tc_a") is not None
        assert api.devices.get("tc_b") is not None
        assert api.devices.get("tc_a") is not api.devices.get("tc_b")

    def test_add_device_generic_quantity(self, api):
        d = api.devices.add_device(quantity="VISIBILITY", xyz=(2, 2, 1), name="smoke01")
        assert isinstance(d, Device)
        assert d.quantity == "VISIBILITY"
        assert d.name == "smoke01"

    def test_add_device_rejects_invalid_quantity(self, api):
        with pytest.raises(ValueError):
            api.devices.add_device(quantity="NOT_A_REAL_QUANTITY", xyz=(0, 0, 0))

    def test_add_device_default_name_when_unnamed(self, api):
        d1 = api.devices.add_device(quantity="VELOCITY", xyz=(0, 0, 0))
        d2 = api.devices.add_device(quantity="VELOCITY", xyz=(1, 0, 0))
        assert d1.name != d2.name

class TestValidationManager:
    def test_validate_clean_project(self, api):
        api.meshes.add_mesh(ijk=(16, 16, 8), xb=(0, 4, 0, 4, 0, 2), id="vm1")
        report = api.validation.validate()
        assert report is not None
        assert report.passed is True

    def test_validate_empty_project_fails(self, api):
        report = api.validation.validate()
        assert report.passed is False

class TestHistoryManager:
    def test_can_undo_after_set_timing(self, api):
        api.set_timing(t_end=300.0)
        assert api.history.can_undo()

    def test_undo_reverses_set_timing(self, api):
        original = api.project.params.t_end
        api.set_timing(t_end=999.0)
        api.history.undo()
        assert api.project.params.t_end == original

    def test_history_labels_not_empty(self, api):
        api.set_timing(t_end=200.0)
        labels = api.history.history()
        assert len(labels) >= 1

    def test_clear_history(self, api):
        api.set_timing(t_end=100.0)
        api.history.clear()
        assert not api.history.can_undo()

class TestApiEvents:
    def test_subscribe_and_receive_event(self, api):
        from pyfds.core.events import EventType
        received = []
        api.subscribe(EventType.OBJECT_ADDED, received.append)
        api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="evt_m")
        assert len(received) >= 1

    def test_unsubscribe_stops_events(self, api):
        from pyfds.core.events import EventType
        received = []
        sub_id = api.subscribe(EventType.OBJECT_ADDED, received.append)
        api.unsubscribe(sub_id)
        api.meshes.add_mesh(ijk=(10, 10, 5), xb=(0, 2, 0, 2, 0, 1), id="no_evt")
        assert len(received) == 0

class TestApiMutators:
    def test_set_timing(self, api):
        api.set_timing(t_end=180.0, t_begin=5.0)
        assert api.project.params.t_end == 180.0
        assert api.project.params.t_begin == 5.0

    def test_set_property_via_dot_path(self, api):
        api.set_property(api.project, "chid", "new_chid")
        assert api.project.chid == "new_chid"

class TestApiInfo:
    def test_info_returns_string(self, api, simple_room_fds_path):
        api.load(simple_room_fds_path)
        info = api.info()
        assert isinstance(info, str)
        assert "simple_room" in info

    def test_snapshot_returns_state_snapshot(self, api):
        from pyfds.core.state import StateSnapshot
        snap = api.snapshot()
        assert isinstance(snap, StateSnapshot)
