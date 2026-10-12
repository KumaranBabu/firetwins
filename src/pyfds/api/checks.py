"""Model checks: running them, switching them on/off, sharing check sets, gating Run.

``api.validation`` is the single entry point adapters use; the rules themselves live
in ``pyfds.validation``.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from .facade import FdsApi

logger = logging.getLogger(__name__)

CHECK_SET_FORMAT = "pyfds-check-set"


class ValidationGateError(RuntimeError):
    """Raised by :meth:`ValidationManager.gate` when the model has validation errors."""

    def __init__(self, report: Any) -> None:
        self.report = report
        super().__init__("Model has validation errors:\n" + "\n".join(report.error_messages))


class ValidationManager:
    """Run validation, manage which checks are active, and gate risky operations."""

    def __init__(self, api: "FdsApi") -> None:
        self._api = api
        self._live_sub_ids: List[int] = []
        self._live_report: Any = None
        self._live_callback: Optional[Callable[[Any], None]] = None
        self._live_min_interval = 0.0
        self._live_last = 0.0

    # -- running -----------------------------------------------------------------
    def validate(self) -> Any:
        """Run every enabled check (see :meth:`set_enabled`)."""
        from pyfds.validation.engine import ValidationEngine
        return ValidationEngine.default().validate(self._api.project)

    def validate_with_plugins(self) -> Any:
        from pyfds.validation.engine import ValidationEngine
        engine = ValidationEngine.default()
        from pyfds.plugins.loader import get_registry
        for rule in get_registry().get_validation_rules():
            engine.add_rule(rule)
        return engine.validate(self._api.project)

    def auto_fix(self) -> Any:
        """Run validation and apply every available auto-fix callable. Returns the report."""
        from pyfds.validation.engine import ValidationEngine
        engine = ValidationEngine.default()
        project = self._api.project
        report = engine.validate(project)
        engine.auto_fix(project, report)
        return report

    # -- gate (anti-corruption layer before Run / export) -------------------------------
    def gate(self) -> Any:
        """Return the report if the model has no validation errors, else raise
        :class:`ValidationGateError`. Warnings never block."""
        report = self.validate()
        if report.errors:
            raise ValidationGateError(report)
        return report

    def can_run(self) -> bool:
        return not self.validate().errors

    # -- model-check sets (Edit Model Checks) ----------------------------------------------
    def checks(self) -> List[Dict[str, Any]]:
        """Every available check: ``[{"name", "description", "enabled"}]``."""
        from pyfds.validation.engine import ValidationEngine
        disabled = set(self._api.project.disabled_checks)
        out = []
        for rule in ValidationEngine.default().rules:
            doc = (type(rule).__doc__ or "").strip().splitlines()
            out.append({"name": rule.name, "description": doc[0].strip() if doc else "",
                        "enabled": rule.name not in disabled})
        return out

    def _known(self) -> List[str]:
        return [c["name"] for c in self.checks()]

    def set_enabled(self, name: str, enabled: bool = True) -> None:
        """Switch one check on or off for this project (undoable, saved with the project)."""
        self.set_enabled_many({name: enabled})

    def set_enabled_many(self, states: Dict[str, bool]) -> None:
        """Change several checks at once as ONE undo step."""
        from pyfds.automation.commands import ModifyPropertyCommand
        known = set(self._known())
        unknown = sorted(n for n in states if n not in known)
        if unknown:
            raise KeyError(f"unknown check(s): {', '.join(unknown)}")
        disabled = list(self._api.project.disabled_checks)
        for name, on in states.items():
            if on and name in disabled:
                disabled.remove(name)
            elif not on and name not in disabled:
                disabled.append(name)
        if disabled == self._api.project.disabled_checks:
            return
        res = self._api.history.execute(
            ModifyPropertyCommand(self._api.project, "disabled_checks", disabled))
        if not res.success:
            raise ValueError(res.message)

    def export_check_set(self, filepath: str, name: str = "") -> str:
        """Write the current on/off state to a small JSON file others can import."""
        data = {"format": CHECK_SET_FORMAT, "version": 1,
                "name": name or Path(filepath).stem,
                "disabled": sorted(self._api.project.disabled_checks)}
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(path)

    def import_check_set(self, filepath: str) -> List[str]:
        """Apply a shared check set. Returns the names in the file this version does not
        know (they are ignored); everything else is applied as one undo step."""
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        if data.get("format") != CHECK_SET_FORMAT:
            raise ValueError(f"{filepath} is not a PyFDS check set")
        known = self._known()
        wanted_off = set(map(str, data.get("disabled", [])))
        self.set_enabled_many({n: n not in wanted_off for n in known})
        return sorted(wanted_off - set(known))

    # -- results -> objects ------------------------------------------------------------------
    def locate(self, result: Any) -> Optional[Any]:
        """The entity a validation result is about (for click-through), or ``None``."""
        name = getattr(result, "entity_name", None)
        if not name:
            return None
        for entity in self._api.project.all_entities:
            if getattr(entity, "name", None) == name:
                return entity
        return None

    # -- live checking while editing ------------------------------------------------------
    @property
    def live_report(self) -> Any:
        """The most recent report produced by live checking (``None`` until the first edit)."""
        return self._live_report

    @property
    def watching(self) -> bool:
        return bool(self._live_sub_ids)

    def watch(self, callback: Optional[Callable[[Any], None]] = None, *,
              min_interval: float = 0.0) -> None:
        """Re-run the checks after every command, undo and redo; keep the result in
        :attr:`live_report` and pass it to *callback*. *min_interval* (seconds) throttles
        re-runs on very large models."""
        from pyfds.core.events import get_global_bus, EventType
        self.unwatch()
        self._live_callback, self._live_min_interval = callback, min_interval
        bus = get_global_bus()
        for et in (EventType.COMMAND_EXECUTED, EventType.UNDO_PERFORMED, EventType.REDO_PERFORMED):
            self._live_sub_ids.append(bus.subscribe(et, self._on_edit))

    def unwatch(self) -> None:
        from pyfds.core.events import get_global_bus
        bus = get_global_bus()
        for sid in self._live_sub_ids:
            bus.unsubscribe(sid)
        self._live_sub_ids = []

    def _on_edit(self, _event: Any) -> None:
        now = time.monotonic()
        if now - self._live_last < self._live_min_interval:
            return
        self._live_last = now
        try:
            self._live_report = self.validate()
        except Exception as exc:                      # live checking must never break editing
            logger.warning("live validation failed: %s", exc)
            return
        if self._live_callback:
            self._live_callback(self._live_report)
