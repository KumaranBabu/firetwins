"""Unit tests — pyfds.core.events (EventBus)."""
from __future__ import annotations

import threading
import time
from typing import List

import pytest
from pyfds.core.events import (
    EventBus, EventType, Event,
    get_global_bus, reset_global_bus,
)


class TestEventBus:
    def setup_method(self):
        self.bus = EventBus(name="test")

    def teardown_method(self):
        self.bus.shutdown()

    # ── subscribe / unsubscribe ─────────────────────────────────────────────

    def test_subscribe_returns_integer_id(self):
        sid = self.bus.subscribe(EventType.OBJECT_ADDED, lambda e: None)
        assert isinstance(sid, int) and sid > 0

    def test_subscription_count_increments(self):
        assert self.bus.subscription_count == 0
        self.bus.subscribe(EventType.OBJECT_ADDED, lambda e: None)
        assert self.bus.subscription_count == 1
        self.bus.subscribe(EventType.OBJECT_REMOVED, lambda e: None)
        assert self.bus.subscription_count == 2

    def test_unsubscribe_removes_callback(self):
        fired = []
        sid = self.bus.subscribe(EventType.OBJECT_ADDED, lambda e: fired.append(1))
        self.bus.unsubscribe(sid)
        self.bus.emit(EventType.OBJECT_ADDED)
        assert fired == []

    def test_unsubscribe_returns_true_when_found(self):
        sid = self.bus.subscribe(EventType.OBJECT_ADDED, lambda e: None)
        assert self.bus.unsubscribe(sid) is True

    def test_unsubscribe_returns_false_for_missing_id(self):
        assert self.bus.unsubscribe(9999) is False

    def test_unsubscribe_all_clears_all(self):
        self.bus.subscribe(EventType.OBJECT_ADDED, lambda e: None)
        self.bus.subscribe(EventType.OBJECT_REMOVED, lambda e: None)
        self.bus.unsubscribe_all()
        assert self.bus.subscription_count == 0

    # ── emit ────────────────────────────────────────────────────────────────

    def test_emit_calls_matching_subscriber(self):
        received: List[Event] = []
        self.bus.subscribe(EventType.OBJECT_ADDED, received.append)
        self.bus.emit(EventType.OBJECT_ADDED, payload={"id": "m1"})
        assert len(received) == 1
        assert received[0].payload == {"id": "m1"}

    def test_emit_does_not_call_mismatched_subscriber(self):
        received = []
        self.bus.subscribe(EventType.OBJECT_REMOVED, received.append)
        self.bus.emit(EventType.OBJECT_ADDED)
        assert received == []

    def test_wildcard_subscriber_receives_all(self):
        received: List[Event] = []
        self.bus.subscribe(None, received.append)
        self.bus.emit(EventType.OBJECT_ADDED)
        self.bus.emit(EventType.PROJECT_SAVED)
        assert len(received) == 2

    def test_multiple_subscribers_same_event(self):
        counts = [0, 0]
        self.bus.subscribe(EventType.VALIDATION_PASSED, lambda e: counts.__setitem__(0, counts[0] + 1))
        self.bus.subscribe(EventType.VALIDATION_PASSED, lambda e: counts.__setitem__(1, counts[1] + 1))
        self.bus.emit(EventType.VALIDATION_PASSED)
        assert counts == [1, 1]

    def test_emit_with_source_label(self):
        received: List[Event] = []
        self.bus.subscribe(EventType.JOB_STARTED, received.append)
        self.bus.emit(EventType.JOB_STARTED, source="SimulationRunner")
        assert received[0].source == "SimulationRunner"

    def test_callback_exception_does_not_propagate(self):
        """Errors in callbacks should be swallowed (logged), not raised."""
        def bad_cb(e):
            raise RuntimeError("intentional")

        self.bus.subscribe(EventType.OBJECT_ADDED, bad_cb)
        # Should not raise:
        self.bus.emit(EventType.OBJECT_ADDED)

    def test_event_timestamp_set(self):
        received: List[Event] = []
        self.bus.subscribe(EventType.OBJECT_ADDED, received.append)
        before = time.monotonic()
        self.bus.emit(EventType.OBJECT_ADDED)
        after = time.monotonic()
        assert before <= received[0].timestamp <= after

    # ── thread safety ────────────────────────────────────────────────────────

    def test_concurrent_emit_does_not_crash(self):
        """Hammering emit from 10 threads should not cause a crash."""
        results = []
        self.bus.subscribe(EventType.CUSTOM, lambda e: results.append(1))
        threads = [
            threading.Thread(target=lambda: self.bus.emit(EventType.CUSTOM))
            for _ in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 10

    # ── subscriptions_for ────────────────────────────────────────────────────

    def test_subscriptions_for_counts_correctly(self):
        self.bus.subscribe(EventType.JOB_COMPLETED, lambda e: None)
        self.bus.subscribe(EventType.JOB_COMPLETED, lambda e: None)
        self.bus.subscribe(None, lambda e: None)   # wildcard counts too
        assert self.bus.subscriptions_for(EventType.JOB_COMPLETED) == 3

    # ── emit_event (pre-built Event) ─────────────────────────────────────────

    def test_emit_event_with_prebuilt_envelope(self):
        received = []
        self.bus.subscribe(EventType.PROJECT_LOADED, received.append)
        evt = Event(type=EventType.PROJECT_LOADED, payload="my_project.fds")
        self.bus.emit_event(evt)
        assert len(received) == 1
        assert received[0].payload == "my_project.fds"

    # ── context manager ──────────────────────────────────────────────────────

    def test_context_manager_shuts_down_cleanly(self):
        with EventBus(name="ctx_test") as bus:
            received = []
            bus.subscribe(EventType.OBJECT_ADDED, received.append)
            bus.emit(EventType.OBJECT_ADDED)
        assert len(received) == 1


class TestGlobalBus:
    def test_get_global_bus_returns_same_instance(self):
        b1 = get_global_bus()
        b2 = get_global_bus()
        assert b1 is b2

    def test_reset_global_bus_creates_new_instance(self):
        b1 = get_global_bus()
        reset_global_bus()
        b2 = get_global_bus()
        assert b1 is not b2

    def test_global_bus_name_is_global(self):
        assert get_global_bus().name == "global"


class TestEventType:
    def test_all_expected_event_types_exist(self):
        expected = [
            "PROJECT_CREATED", "PROJECT_LOADED", "PROJECT_SAVED",
            "OBJECT_ADDED", "OBJECT_REMOVED", "OBJECT_MODIFIED",
            "COMMAND_EXECUTED", "UNDO_PERFORMED", "REDO_PERFORMED",
            "VALIDATION_STARTED", "VALIDATION_PASSED", "VALIDATION_FAILED",
            "JOB_QUEUED", "JOB_STARTED", "JOB_COMPLETED", "JOB_FAILED",
            "BATCH_STARTED", "BATCH_COMPLETED",
            "RESULTS_INDEXED", "RESULTS_LOADED",
            "SMV_LAUNCHED", "SMV_EXITED", "SMV_SCRIPT_SAVED",
            "PLUGIN_LOADED", "PLUGIN_UNLOADED",
            "CONFIG_CHANGED", "CUSTOM",
        ]
        names = {e.name for e in EventType}
        for name in expected:
            assert name in names, f"EventType.{name} missing"

    def test_event_types_are_unique(self):
        values = [e.value for e in EventType]
        assert len(values) == len(set(values))
