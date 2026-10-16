"""
PyFDS Scenario System
=====================
Scenarios let you define named variants of a simulation by storing per-entity
field overrides without duplicating the whole project.  Applying a scenario
temporarily patches the project entities; resetting restores the originals.

Classes
-------
Scenario       — named variant: a set of per-entity field overrides
ScenarioStore  — in-memory registry used by ScenarioManager
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Scenario:
    """
    A named simulation variant.

    ``overrides`` maps entity UIDs to ``{field_name: override_value}`` dicts.
    Overrides are applied to project entities when :meth:`ScenarioStore.apply`
    is called; the originals are snapshotted so they can be restored.

    Example::

        store = ScenarioStore()
        s = store.create("high_hrr", description="Peak HRR case")
        store.set_override(s, burner_entity, "heat_release_rate", 2000.0)
        store.apply(api.project, "high_hrr")
        # ... analyse / run ...
        store.reset(api.project)
    """
    name: str
    description: str = ""
    overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def add_override(self, entity_uid: str, field_name: str, value: Any) -> None:
        """Register an override for *entity_uid*.*field_name* = *value*."""
        self.overrides.setdefault(entity_uid, {})[field_name] = value

    def remove_override(self, entity_uid: str, field_name: str) -> None:
        """Remove the override for *entity_uid*.*field_name* if present."""
        bucket = self.overrides.get(entity_uid, {})
        bucket.pop(field_name, None)
        if not bucket:
            self.overrides.pop(entity_uid, None)

    def override_count(self) -> int:
        return sum(len(v) for v in self.overrides.values())


class ScenarioStore:
    """
    In-memory store for scenario objects.

    Tracks which scenario is active and holds snapshots of original entity
    values so that :meth:`reset` can restore them.
    """

    def __init__(self) -> None:
        self._scenarios: Dict[str, Scenario] = {}
        self._active: Optional[str] = None
        # Snapshots: {entity_uid: {field: original_value}}
        self._snapshots: Dict[str, Dict[str, Any]] = {}

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(self, name: str, description: str = "") -> Scenario:
        """Create and register a new scenario; raises ``ValueError`` if name exists."""
        if name in self._scenarios:
            raise ValueError(f"Scenario {name!r} already exists.")
        s = Scenario(name=name, description=description)
        self._scenarios[name] = s
        return s

    def clone(self, base_name: str, new_name: str) -> Scenario:
        """Deep-copy *base_name* scenario as *new_name*."""
        base = self.get(base_name)
        if base is None:
            raise KeyError(f"Scenario {base_name!r} not found.")
        if new_name in self._scenarios:
            raise ValueError(f"Scenario {new_name!r} already exists.")
        cloned = Scenario(
            name=new_name,
            description=base.description,
            overrides=copy.deepcopy(base.overrides),
            tags=list(base.tags),
        )
        self._scenarios[new_name] = cloned
        return cloned

    def get(self, name: str) -> Optional[Scenario]:
        return self._scenarios.get(name)

    def rename(self, old: str, new: str) -> Scenario:
        """Give a scenario a new name, keeping its place in the list."""
        s = self.get(old)
        if s is None:
            raise KeyError(f"Scenario {old!r} not found.")
        if new == old:
            return s
        if not new.strip():
            raise ValueError("A scenario needs a name.")
        if new in self._scenarios:
            raise ValueError(f"Scenario {new!r} already exists.")
        if old == self._active:
            raise RuntimeError(f"Cannot rename active scenario {old!r}. Call reset() first.")
        s.name = new
        items = [(new if k == old else k, v) for k, v in self._scenarios.items()]
        self._scenarios.clear()
        self._scenarios.update(items)
        return s

    def remove_override(self, scenario_name: str, entity: Any, field_name: str) -> None:
        s = self._scenarios.get(scenario_name)
        if s is None:
            raise KeyError(f"Scenario {scenario_name!r} not found.")
        uid = entity.uid if hasattr(entity, "uid") else str(id(entity))
        if field_name not in s.overrides.get(uid, {}):
            raise KeyError(f"{scenario_name!r} has no override of {field_name!r}")
        s.remove_override(uid, field_name)

    def all(self) -> List[Scenario]:
        return list(self._scenarios.values())

    def delete(self, name: str) -> None:
        if name == self._active:
            raise RuntimeError(
                f"Cannot delete active scenario {name!r}. Call reset() first."
            )
        self._scenarios.pop(name, None)

    def set_override(
        self, scenario_name: str, entity: Any, field_name: str, value: Any
    ) -> None:
        """Record that *entity*.*field_name* should be *value* in *scenario_name*."""
        s = self._scenarios.get(scenario_name)
        if s is None:
            raise KeyError(f"Scenario {scenario_name!r} not found.")
        uid = entity.uid if hasattr(entity, "uid") else str(id(entity))
        s.add_override(uid, field_name, value)

    # ── Apply / reset ─────────────────────────────────────────────────────────

    def apply(self, project: Any, name: str) -> None:
        """
        Apply scenario *name* to *project*.

        Snapshots current entity values before patching so :meth:`reset` can
        restore them.  Raises ``RuntimeError`` if another scenario is already
        active.
        """
        if self._active is not None:
            raise RuntimeError(
                f"Scenario {self._active!r} is already active. "
                "Call reset() before applying a different scenario."
            )
        s = self._scenarios.get(name)
        if s is None:
            raise KeyError(f"Scenario {name!r} not found.")

        # Build uid → entity map from project
        entity_map = _build_uid_map(project)

        self._snapshots.clear()
        for uid, overrides in s.overrides.items():
            entity = entity_map.get(uid)
            if entity is None:
                continue
            snap: Dict[str, Any] = {}
            for fname, new_val in overrides.items():
                snap[fname] = getattr(entity, fname, None)
                setattr(entity, fname, new_val)
            self._snapshots[uid] = snap

        self._active = name

    def reset(self, project: Any) -> None:
        """Restore all entity values patched by :meth:`apply`."""
        entity_map = _build_uid_map(project)
        for uid, snap in self._snapshots.items():
            entity = entity_map.get(uid)
            if entity is None:
                continue
            for fname, old_val in snap.items():
                setattr(entity, fname, old_val)
        self._snapshots.clear()
        self._active = None

    # ── State capture (used by the undo system) ───────────────────────────────

    def capture_state(self, project: Any) -> Dict[str, Any]:
        """Deep snapshot of the registry plus every entity field a scenario
        can touch, so apply/reset/edit operations can be undone exactly."""
        uids = set(self._snapshots)
        for s in self._scenarios.values():
            uids.update(s.overrides)
        entity_map = _build_uid_map(project)
        values: Dict[str, Dict[str, Any]] = {}
        for uid in uids:
            entity = entity_map.get(uid)
            if entity is None:
                continue
            fields = set(self._snapshots.get(uid, {}))
            for s in self._scenarios.values():
                fields.update(s.overrides.get(uid, {}))
            values[uid] = {f: copy.deepcopy(getattr(entity, f, None)) for f in fields}
        return {
            "scenarios": copy.deepcopy(self._scenarios),
            "active": self._active,
            "snapshots": copy.deepcopy(self._snapshots),
            "values": values,
        }

    def restore_state(self, project: Any, state: Dict[str, Any]) -> None:
        """Put back a snapshot produced by :meth:`capture_state`."""
        entity_map = _build_uid_map(project)
        for uid, fields in state["values"].items():
            entity = entity_map.get(uid)
            if entity is None:
                continue
            for fname, val in fields.items():
                setattr(entity, fname, copy.deepcopy(val))
        self._scenarios.clear()
        self._scenarios.update(copy.deepcopy(state["scenarios"]))
        self._snapshots.clear()
        self._snapshots.update(copy.deepcopy(state["snapshots"]))
        self._active = state["active"]

    @property
    def active(self) -> Optional[str]:
        """Name of the currently active scenario, or ``None``."""
        return self._active


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_uid_map(project: Any) -> Dict[str, Any]:
    """Return ``{uid: entity}`` for every entity in every project collection."""
    uid_map: Dict[str, Any] = {}
    for collection_name in dir(project):
        if collection_name.startswith("_"):
            continue
        try:
            col = getattr(project, collection_name)
        except Exception:
            continue
        if not isinstance(col, list):
            continue
        for item in col:
            if hasattr(item, "uid"):
                uid_map[item.uid] = item
    return uid_map
