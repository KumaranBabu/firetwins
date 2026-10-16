"""Scenario management.

Split out of the former monolithic ``controller.py``; behaviour unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import _UndoableStore


if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)


class ScenarioManager(_UndoableStore):
    """
    Manage named simulation variants (scenarios).

    Scenarios store per-entity field overrides that can be applied to the
    active project and reversed without duplicating the project.

    Accessible via ``api.scenarios``.

    Example::

        s = api.scenarios.create("high_hrr", "Peak 2 MW case")
        api.scenarios.set_override("high_hrr", burner, "heat_release_rate", 2000.0)
        api.scenarios.apply("high_hrr")
        # run simulation …
        api.scenarios.reset()
    """

    def __init__(self, api: "FdsApi") -> None:
        self._api = api

    @property
    def _store(self):
        """The active project's scenario store (one per open document)."""
        return self._api.project.editor.scenarios

    # undo support: the store plus every entity field a scenario can touch
    def _capture_state(self):
        return self._store.capture_state(self._api.project)

    def _restore_state(self, state) -> None:
        self._store.restore_state(self._api.project, state)

    def create(self, name: str, description: str = "") -> Any:
        """Create and return a new :class:`~pyfds.domain.scenario.Scenario`."""
        return self._do(f"create scenario {name!r}", lambda: self._store.create(name, description))

    def clone(self, base_name: str, new_name: str) -> Any:
        """Deep-copy scenario *base_name* as *new_name*."""
        return self._do(f"clone scenario {base_name!r} as {new_name!r}", lambda: self._store.clone(base_name, new_name))

    def get(self, name: str) -> Optional[Any]:
        """Return the scenario by *name*, or None."""
        return self._store.get(name)

    def all(self) -> List[Any]:
        """Return all registered scenarios."""
        return self._store.all()

    def delete(self, name: str) -> None:
        """Delete scenario *name*. Raises if it is currently active."""
        self._do(f"delete scenario {name!r}", lambda: self._store.delete(name))

    def set_override(
        self, scenario_name: str, entity: Any, field_name: str, value: Any
    ) -> None:
        """Record that *entity*.*field_name* should equal *value* in *scenario_name*."""
        self._do(
            f"scenario {scenario_name!r}: override {field_name} = {value!r}",
            lambda: self._store.set_override(scenario_name, entity, field_name, value),
        )

    def update(self, name: str, *, new_name: Optional[str] = None, description: Optional[str] = None,
               tags: Optional[List[str]] = None) -> Any:
        """Rename a scenario and/or change its description or tags (one undo step). Not allowed while it is applied."""
        def edit():
            s = self._store.get(name)
            if s is None:
                raise KeyError(f"Scenario {name!r} not found.")
            if new_name is not None:
                self._store.rename(name, new_name)
            if description is not None:
                s.description = description
            if tags is not None:
                s.tags = [str(t).strip() for t in tags if str(t).strip()]
            return s
        return self._do(f"edit scenario {name!r}", edit)

    def remove_override(self, scenario_name: str, entity: Any, field_name: str) -> None:
        """Forget that *scenario_name* changes *entity*.*field_name*."""
        self._do(f"scenario {scenario_name!r}: drop override {field_name}",
                 lambda: self._store.remove_override(scenario_name, entity, field_name))

    def overrides(self, name: str) -> List[Dict[str, Any]]:
        """What scenario *name* changes: ``[{"entity", "kind", "field", "value", "uid"}]`` (``entity`` is ``None``
        when the object no longer exists in the project)."""
        s = self._store.get(name)
        if s is None:
            raise KeyError(f"Scenario {name!r} not found.")
        from pyfds.domain.scenario import _build_uid_map
        by_uid = _build_uid_map(self._api.project)
        return [{"entity": by_uid.get(uid), "kind": type(by_uid[uid]).__name__ if uid in by_uid else "",
                 "field": f, "value": v, "uid": uid}
                for uid, fields in s.overrides.items() for f, v in fields.items()]

    DEFINITIONS_FORMAT = "pyfds-scenarios"

    def export_definitions(self, filepath: str) -> int:
        """Write every scenario (name, description, tags and what it changes) to a JSON file. Objects are named by
        type and name, not by internal id, so the file can be imported into another version of the model."""
        import json
        from pathlib import Path
        out = []
        for s in self.all():
            changes = []
            for o in self.overrides(s.name):
                if o["entity"] is None:
                    continue
                changes.append({"type": o["kind"], "name": getattr(o["entity"], "name", ""), "field": o["field"],
                                "value": o["value"]})
            out.append({"name": s.name, "description": s.description, "tags": list(s.tags), "changes": changes})
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"format": self.DEFINITIONS_FORMAT, "version": 1, "scenarios": out}, indent=2,
                                   default=list), encoding="utf-8")
        return len(out)

    def import_definitions(self, filepath: str, overwrite: bool = False) -> Dict[str, Any]:
        """Add the scenarios of a definitions file (one undo step). A change is applied to the object of the same
        type and name in this model; changes with no such object are reported in ``missing`` and left out.
        Existing scenarios of the same name are skipped, or replaced with ``overwrite=True`` (never the applied one).
        Returns ``{"added", "replaced", "skipped", "missing"}``."""
        import json
        from pathlib import Path
        try:
            doc = json.loads(Path(filepath).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read {filepath}: {exc}") from None
        if not isinstance(doc, dict) or doc.get("format") != self.DEFINITIONS_FORMAT:
            raise ValueError(f"{filepath} is not a PyFDS scenario definitions file")
        by_key = {(type(e).__name__, getattr(e, "name", None)): e for e in self._api.project.all_entities}
        report: Dict[str, Any] = {"added": [], "replaced": [], "skipped": [], "missing": []}
        with self._api.history.transaction("import scenarios"):
            for sc in doc.get("scenarios", []):
                name = str(sc.get("name", "")).strip()
                if not name:
                    continue
                exists = self.get(name) is not None
                if exists and not overwrite:
                    report["skipped"].append(name)
                    continue
                if exists:
                    if name == self.active:
                        report["skipped"].append(name)
                        continue
                    self.delete(name)
                self.create(name, str(sc.get("description", "")))
                self.update(name, tags=[str(t) for t in sc.get("tags", [])])
                for ch in sc.get("changes", []):
                    ent = by_key.get((ch.get("type"), ch.get("name")))
                    if ent is None or ch.get("field") not in type(ent).model_fields:
                        report["missing"].append(f"{name}: {ch.get('type')} {ch.get('name')} . {ch.get('field')}")
                        continue
                    self.set_override(name, ent, ch["field"], ch.get("value"))
                report["replaced" if exists else "added"].append(name)
        return report

    def apply(self, name: str) -> None:
        """Apply scenario *name* to the active project."""
        self._do(f"apply scenario {name!r}", lambda: self._store.apply(self._api.project, name))

    def reset(self) -> None:
        """Restore all entity values patched by the active scenario."""
        self._do("reset scenario", lambda: self._store.reset(self._api.project))

    @property
    def active(self) -> Optional[str]:
        """Name of the currently active scenario, or None."""
        return self._store.active

    def remove(self, entity: Any) -> None:
        """Alias for ``delete(entity.name)`` — lets Scenario rows go through
        the same generic "Delete Selected" path as every other entity type."""
        self.delete(entity.name)

    def export_all(self, dirpath: str, *, num_processes: int = 1,
                   fds_command: Optional[str] = None) -> Dict[str, str]:
        """
        Apply each registered scenario in turn, write the resulting project
        to its own ``<dirpath>/<scenario_name>/<scenario_name>.fds``, then
        reset — so every named variant ends up as an independent .fds file
        without ever leaving two scenarios applied at once.

        Also writes ``run_all.bat`` and ``run_all.sh`` into *dirpath*: they run every
        scenario in sequence (``mpiexec -n N`` when *num_processes* > 1; *fds_command*
        defaults to the configured ``fds_binary``, else ``fds`` from PATH).

        Returns a ``{scenario_name: filepath}`` dict of the files written.
        Raises ``RuntimeError`` if a scenario is already active (call
        ``reset()`` first) so a partially-patched project is never exported.
        """
        if self.active is not None:
            raise RuntimeError(
                f"Scenario {self.active!r} is already active. "
                "Call reset() before export_all()."
            )
        from pathlib import Path
        from pyfds.io.fds_writer import FdsWriter
        writer = FdsWriter()
        written: Dict[str, str] = {}
        for scenario in self.all():
            self._store.apply(self._api.project, scenario.name)
            try:
                path = Path(dirpath) / scenario.name / f"{scenario.name}.fds"
                writer.write(self._api.project, str(path))
                written[scenario.name] = str(path)
            finally:
                self._store.reset(self._api.project)
        if written:
            command = fds_command or getattr(self._api.config, "fds_binary", None) or "fds"
            self.write_run_scripts(dirpath, list(written), command, num_processes)
        return written

    @staticmethod
    def write_run_scripts(dirpath: str, names: List[str], fds_command: str = "fds",
                          num_processes: int = 1) -> Dict[str, str]:
        """Write ``run_all.bat`` / ``run_all.sh`` that run ``<name>/<name>.fds`` for each name
        in order, carrying on after a failed scenario and reporting it. Returns the script paths."""
        from pathlib import Path
        if num_processes < 1:
            raise ValueError("num_processes must be >= 1")
        root = Path(dirpath)
        mpi = f"mpiexec -n {num_processes} " if num_processes > 1 else ""
        bat = ["@echo off", "rem Generated by PyFDS: runs every scenario in sequence.",
               "setlocal", f'set "FDS={fds_command}"', "set FAILED=0"]
        sh = ["#!/bin/sh", "# Generated by PyFDS: runs every scenario in sequence.",
              f'FDS="{fds_command}"', "FAILED=0"]
        for n in names:
            bat += [f'echo === {n} ===', f'pushd "%~dp0{n}"', f'{mpi}"%FDS%" {n}.fds',
                    f'if errorlevel 1 (echo Scenario {n} FAILED & set FAILED=1)', "popd"]
            sh += [f'echo "=== {n} ==="', f'(cd "$(dirname "$0")/{n}" && {mpi}"$FDS" {n}.fds) || '
                   f'{{ echo "Scenario {n} FAILED"; FAILED=1; }}']
        bat += ["exit /b %FAILED%"]
        sh += ['exit "$FAILED"']
        paths = {"bat": root / "run_all.bat", "sh": root / "run_all.sh"}
        paths["bat"].write_text("\r\n".join(bat) + "\r\n", encoding="utf-8", newline="")
        paths["sh"].write_text("\n".join(sh) + "\n", encoding="utf-8", newline="")
        return {k: str(v) for k, v in paths.items()}
