"""
PyFDS Validation Engine
=======================
A pluggable, rule-based validation framework.

Design
------
* ``ValidationRule`` is a Protocol (structural typing) so any class with a
  ``check(project) → List[ValidationResult]`` method qualifies as a rule.
* ``ValidationEngine`` aggregates rules, runs them all, and returns a combined
  report.  Rules can be added, removed, or replaced at runtime — including by
  external plugins.
* ``Severity`` distinguishes errors (sim will likely crash) from warnings
  (sim may run but give wrong results) and info messages.

GUI contract
------------
The engine emits its results through the event bus so a future GUI can
show a live validation panel without coupling to the engine directly.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class Severity(Enum):
    ERROR   = auto()
    WARNING = auto()
    INFO    = auto()


@dataclass
class ValidationResult:
    """A single finding from a validation rule."""
    severity: Severity
    rule: str                       # rule class name
    message: str
    entity_name: Optional[str] = None   # which entity triggered this
    hint: Optional[str] = None          # optional remediation hint
    fix: Optional[Any] = None           # Callable[[FdsProject], None] — auto-fix if available

    def __str__(self) -> str:
        prefix = {
            Severity.ERROR:   "[ERROR]",
            Severity.WARNING: "[WARN] ",
            Severity.INFO:    "[INFO] ",
        }[self.severity]
        entity = f" ({self.entity_name})" if self.entity_name else ""
        return f"{prefix} {self.message}{entity}"


@dataclass
class ValidationReport:
    """Aggregated results from a full validation pass."""
    project_chid: str
    elapsed_seconds: float
    results: List[ValidationResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.monotonic)

    @property
    def errors(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == Severity.WARNING]

    @property
    def infos(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == Severity.INFO]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_messages(self) -> List[str]:
        return [r.message for r in self.errors]

    def summary(self) -> str:
        e, w, i = len(self.errors), len(self.warnings), len(self.infos)
        status = "PASS" if self.passed else "FAIL"
        return (f"[{status}] Validation: {e} error(s), {w} warning(s), "
                f"{i} info(s) in {self.elapsed_seconds:.3f}s")

    def __str__(self) -> str:
        lines = [self.summary()]
        for r in self.results:
            lines.append(f"  {r}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rule protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ValidationRule(Protocol):
    """
    Protocol that every validation rule must implement.

    Structural subtyping: any class with a matching ``check`` signature
    qualifies automatically — no inheritance required.
    """
    @property
    def name(self) -> str:
        """Human-readable rule identifier."""
        ...

    def check(self, project: Any) -> List[ValidationResult]:
        """
        Inspect *project* and return a (possibly empty) list of findings.

        Must not raise; instead return an ERROR-severity result on internal failure.
        """
        ...


# ---------------------------------------------------------------------------
# Validation Engine
# ---------------------------------------------------------------------------

class _MeshCopiesView:
    """The project with ``meshes`` replaced by the expanded set; everything else is read from the project itself."""

    def __init__(self, project: Any, meshes: List[Any]) -> None:
        self.__dict__["_project"] = project
        self.__dict__["meshes"] = meshes

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__dict__["_project"], name)


def _with_mesh_copies(project: Any) -> Any:
    if not any(getattr(m, "mult_id", None) for m in getattr(project, "meshes", [])):
        return project
    from pyfds.domain.mesh_copies import expanded_meshes
    return _MeshCopiesView(project, expanded_meshes(project))


class ValidationEngine:
    """
    Runs a configurable set of ``ValidationRule`` objects against an
    ``FdsProject`` and returns a ``ValidationReport``.

    Usage::

        engine = ValidationEngine()
        engine.add_rule(PoissonComplianceRule())
        engine.add_rule(MeshOverlapRule())

        report = engine.validate(project)
        if not report.passed:
            for err in report.errors:
                print(err)

    Plugin integration::

        engine.add_rule(MyCustomPlugin().as_rule())

    GUI integration::

        from pyfds.core.events import get_global_bus, EventType
        def on_validation(event):
            update_panel(event.payload)
        get_global_bus().subscribe(EventType.VALIDATION_FAILED, on_validation)
    """

    def __init__(self, *, emit_events: bool = True) -> None:
        self._rules: List[ValidationRule] = []
        self._emit_events = emit_events

    # ── Rule management ────────────────────────────────────────────────────

    def add_rule(self, rule: ValidationRule) -> "ValidationEngine":
        """Append *rule* to the pipeline. Returns self for chaining."""
        self._rules.append(rule)
        logger.debug("ValidationEngine: added rule %s", rule.name)
        return self

    def remove_rule(self, name: str) -> bool:
        """Remove the first rule whose ``name`` matches. Returns True if found."""
        for i, r in enumerate(self._rules):
            if r.name == name:
                del self._rules[i]
                return True
        return False

    def replace_rule(self, name: str, new_rule: ValidationRule) -> bool:
        """Replace an existing rule by name. Returns True if replaced."""
        for i, r in enumerate(self._rules):
            if r.name == name:
                self._rules[i] = new_rule
                return True
        return False

    @property
    def rules(self) -> List[ValidationRule]:
        """Read-only view of the registered rule objects."""
        return list(self._rules)

    @property
    def rule_names(self) -> List[str]:
        return [r.name for r in self._rules]

    def clear_rules(self) -> None:
        self._rules.clear()

    # ── Validation ─────────────────────────────────────────────────────────

    def validate(self, project: Any) -> ValidationReport:
        """
        Run all registered rules against *project*.

        Returns a ``ValidationReport`` regardless of pass/fail.
        Never raises; rule-level exceptions are captured as ERROR results.
        """
        t0 = time.monotonic()
        all_results: List[ValidationResult] = []

        disabled = set(getattr(project, "disabled_checks", None) or ())
        seen = _with_mesh_copies(project)            # the rules see every mesh a multiplier makes, not only the one typed in
        for rule in self._rules:
            if rule.name in disabled:
                continue
            try:
                results = rule.check(seen)
                all_results.extend(results)
            except Exception as exc:
                logger.error("Rule %s raised unexpectedly: %s", rule.name, exc,
                             exc_info=True)
                all_results.append(ValidationResult(
                    severity=Severity.ERROR,
                    rule=rule.name,
                    message=f"Rule execution error: {exc}",
                    hint="This is a bug in the rule implementation.",
                ))

        elapsed = time.monotonic() - t0
        report = ValidationReport(
            project_chid=getattr(project, "chid", "?"),
            elapsed_seconds=elapsed,
            results=all_results,
        )

        # Emit events
        if self._emit_events:
            self._emit(report)

        logger.debug("Validation: %s", report.summary())
        return report

    def _emit(self, report: ValidationReport) -> None:
        try:
            from pyfds.core.events import get_global_bus, EventType
            bus = get_global_bus()
            if report.passed:
                bus.emit(EventType.VALIDATION_PASSED, report, source="ValidationEngine")
            else:
                bus.emit(EventType.VALIDATION_FAILED, report, source="ValidationEngine")
        except Exception:
            pass  # events are best-effort

    def auto_fix(self, project: Any, report: "ValidationReport") -> int:
        """
        Apply all available auto-fixes from *report* to *project*.

        Each ``ValidationResult`` with a non-None ``fix`` callable is invoked
        as ``result.fix(project)``.  Failures are logged but do not abort
        remaining fixes.

        Returns the number of fixes successfully applied.
        """
        count = 0
        for result in report.results:
            if result.fix is not None:
                try:
                    result.fix(project)
                    count += 1
                    logger.info("Auto-fix applied for rule '%s': %s",
                                result.rule, result.message)
                except Exception as exc:
                    logger.warning("Auto-fix for rule '%s' failed: %s", result.rule, exc)
        return count

    # ── Factory: default full suite ────────────────────────────────────────

    @classmethod
    def default(cls) -> "ValidationEngine":
        """Return an engine pre-loaded with all built-in rules."""
        from .rules import (
            MeshPresenceRule,
            PoissonComplianceRule, MpiRankGapRule, MeshAlignmentRule,
            MeshOverlapRule, DanglingSurfaceRule, HoleContainmentRule,
            HvacNodeReferenceRule, RampMonotonicityRule,
            ReferenceIntegrityRule, FireResolutionRule, ObstBoundsRule,
            HvacTopologyRule,
            # Gap-fill additions
            DuplicateIdRule, VentCoplanarRule, DeviceBoundsRule,
            SurfaceLayerRule, CtrlLoopRule, ControlFunctionRule, FuelSpeciesRule,
            BackingValueRule, MeshAspectRatioRule, InitBoundsRule,
            SliceBoundsRule, CylindricalMeshRule,
            SurfaceTypeRule, LiquidFuelRule, ComplexReactionRule,
            DeviceSystemRule, HvacLayoutRule, ParticleKindRule, MaterialResidueRule,
        )
        engine = cls()
        for rule_cls in [
            MeshPresenceRule,
            PoissonComplianceRule, MpiRankGapRule, MeshAlignmentRule,
            MeshOverlapRule, DanglingSurfaceRule, HoleContainmentRule,
            HvacNodeReferenceRule, RampMonotonicityRule,
            ReferenceIntegrityRule, FireResolutionRule, ObstBoundsRule,
            HvacTopologyRule,
            # Gap-fill additions
            DuplicateIdRule, VentCoplanarRule, DeviceBoundsRule,
            SurfaceLayerRule, CtrlLoopRule, ControlFunctionRule, FuelSpeciesRule,
            BackingValueRule, MeshAspectRatioRule, InitBoundsRule,
            SliceBoundsRule, CylindricalMeshRule,
            SurfaceTypeRule, LiquidFuelRule, ComplexReactionRule,
            DeviceSystemRule, HvacLayoutRule, ParticleKindRule, MaterialResidueRule,
        ]:
            engine.add_rule(rule_cls())
        return engine
