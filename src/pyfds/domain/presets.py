"""
PyFDS Preset / Template Engine
================================
Pre-built fire scenario templates that produce a partially-configured
``FdsProject`` ready for geometry and device placement.

Usage::

    from pyfds.domain.presets import PresetEngine, list_presets

    eng = PresetEngine()
    print(list_presets())

    project = eng.apply("room_fire", hrr_kw=500, t_end=120.0)
    # project is a populated FdsProject; caller adds geometry, saves, runs.

Adding custom templates::

    @eng.register("my_scenario")
    def my_scenario(project, **kwargs):
        ...
        return project
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .model import FdsProject
from .geometry import GeometryHelper as _GH

from .presets_common import (  # noqa: F401  (re-exported)
    _auto_cells,
)
from .presets_builders import (  # noqa: F401  (re-exported)
    _build_atrium_smoke,
    _build_blank,
    _build_corridor_smoke,
    _build_pool_fire,
    _build_room_fire,
    _build_wildland_fire,
)


logger = logging.getLogger(__name__)


@dataclass
class ScenarioTemplate:
    name: str
    description: str
    tags: List[str]
    defaults: Dict[str, Any]
    builder: Callable[..., FdsProject]

    def apply(self, **kwargs) -> FdsProject:
        merged = {**self.defaults, **kwargs}
        return self.builder(**merged)


class PresetEngine:
    """Registry and executor of scenario templates."""

    def __init__(self) -> None:
        self._registry: Dict[str, ScenarioTemplate] = {}
        self._register_builtins()

    # ── Registration ─────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        defaults: Optional[Dict[str, Any]] = None,
    ) -> Callable:
        """Decorator to register a builder function as a named template."""
        def decorator(fn: Callable) -> Callable:
            self._registry[name] = ScenarioTemplate(
                name=name,
                description=description or fn.__doc__ or "",
                tags=tags or [],
                defaults=defaults or {},
                builder=fn,
            )
            return fn
        return decorator

    def add(self, template: ScenarioTemplate) -> None:
        self._registry[template.name] = template

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[ScenarioTemplate]:
        return self._registry.get(name)

    def apply(self, name: str, **kwargs) -> FdsProject:
        """
        Build and return a project from the named template.

        Parameters
        ----------
        name:
            Template identifier (see ``list_presets()``).
        **kwargs:
            Override template default parameters.

        Raises
        ------
        KeyError:
            If *name* is not a registered template.
        """
        tmpl = self._registry.get(name)
        if tmpl is None:
            raise KeyError(
                f"No preset named {name!r}. "
                f"Available: {sorted(self._registry)}"
            )
        project = tmpl.apply(**kwargs)
        logger.info("Preset %r applied → project chid=%r", name, project.chid)
        return project

    def names(self) -> List[str]:
        return sorted(self._registry.keys())

    def all_templates(self) -> List[ScenarioTemplate]:
        return list(self._registry.values())

    # ── Built-in presets ──────────────────────────────────────────────────────

    def _register_builtins(self) -> None:
        # ── Room fire ──────────────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="room_fire",
            description="Single compartment room fire with a single burner and thermocouples.",
            tags=["compartment", "residential", "beginner"],
            defaults={
                "chid":       "room_fire",
                "t_end":      60.0,
                "hrr_kw":     250.0,
                "room_x":     5.0,
                "room_y":     4.0,
                "room_z":     3.0,
                "cell_size":  0.1,
            },
            builder=_build_room_fire,
        ))

        # ── Corridor smoke ─────────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="corridor_smoke",
            description="Smoke spread in a long corridor with a doorway fire source.",
            tags=["egress", "smoke", "corridor"],
            defaults={
                "chid":      "corridor_smoke",
                "t_end":     120.0,
                "hrr_kw":    100.0,
                "length":    20.0,
                "width":     2.0,
                "height":    2.5,
                "cell_size": 0.1,
            },
            builder=_build_corridor_smoke,
        ))

        # ── Pool fire ──────────────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="pool_fire",
            description="Circular pool fire (heptane) in open domain for heat flux studies.",
            tags=["pool", "heptane", "validation"],
            defaults={
                "chid":        "pool_fire",
                "t_end":       60.0,
                "pool_dia":    0.3,
                "hrr_kw":      50.0,
                "domain_size": 3.0,
                "cell_size":   0.05,
            },
            builder=_build_pool_fire,
        ))

        # ── Atrium smoke filling ───────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="atrium_smoke",
            description="Smoke filling in a tall atrium with mechanical exhaust.",
            tags=["atrium", "smoke", "hvac"],
            defaults={
                "chid":       "atrium_smoke",
                "t_end":      180.0,
                "hrr_kw":     1000.0,
                "width":      20.0,
                "depth":      20.0,
                "height":     15.0,
                "cell_size":  0.25,
            },
            builder=_build_atrium_smoke,
        ))

        # ── Wildland interface ─────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="wildland_fire",
            description="Wind-driven grass fire approaching a structure.",
            tags=["wui", "outdoor", "wind"],
            defaults={
                "chid":       "wildland_fire",
                "t_end":      60.0,
                "wind_speed": 5.0,
                "domain_x":   50.0,
                "domain_y":   20.0,
                "domain_z":   10.0,
                "cell_size":  0.2,
            },
            builder=_build_wildland_fire,
        ))

        # ── Blank project ─────────────────────────────────────────────────
        self.add(ScenarioTemplate(
            name="blank",
            description="Empty FdsProject with sensible global defaults only.",
            tags=["generic"],
            defaults={"chid": "new_case", "t_end": 60.0},
            builder=_build_blank,
        ))


_GH.auto_cell_count_from_box = staticmethod(_auto_cells)


_default_engine = PresetEngine()


def list_presets() -> List[str]:
    """Return the names of all registered built-in templates."""
    return _default_engine.names()


def apply_preset(name: str, **kwargs) -> FdsProject:
    """Apply a named preset using the default engine."""
    return _default_engine.apply(name, **kwargs)
