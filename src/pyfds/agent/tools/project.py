"""Simulation parameters, validation, templates, undo/redo history and project info."""
from __future__ import annotations

from typing import List

from .base import ToolSpec, _configure_simulation_params


TOOLS: List[ToolSpec] = [

    # ── Simulation parameters ───────────────────────────────────────────────
    ToolSpec(
        name="configure_simulation_params",
        description="Set simulation time span and stepping control (&TIME namelist): T_BEGIN, T_END, DT, RESTRICT_TIME_STEP.",
        input_schema={
            "type": "object",
            "properties": {
                "t_end": {"type": "number", "default": 60.0, "description": "Simulation end time, s."},
                "t_begin": {"type": "number", "default": 0.0, "description": "Simulation start time, s."},
                "dt": {"type": "number", "description": "Initial/fixed time step, s. Leave blank for FDS auto."},
                "restrict_time_step": {"type": "boolean", "default": True},
            },
            "required": ["t_end"],
        },
        handler=lambda api, t_end, t_begin=0.0, dt=None, restrict_time_step=True: _configure_simulation_params(
            api, t_end, t_begin, dt, restrict_time_step
        ),
    ),

    # ── Validation ───────────────────────────────────────────────────────────
    ToolSpec(
        name="validate_project",
        description="Run all validation rules against the active project and return the report.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.validation.validate(),
        mutates=False,
    ),
    ToolSpec(
        name="auto_fix_project",
        description="Run validation and apply every available auto-fix. Returns the (post-fix) report.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.validation.auto_fix(),
    ),

    # ── Templates ────────────────────────────────────────────────────────────
    ToolSpec(
        name="list_templates",
        description="List built-in and plugin-contributed scenario presets.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.templates.list_presets(),
        mutates=False,
    ),
    ToolSpec(
        name="apply_template",
        description="Apply a named scenario preset, replacing the active project.",
        input_schema={"type": "object", "properties": {"preset_name": {"type": "string"}}, "required": ["preset_name"]},
        handler=lambda api, preset_name: api.templates.apply(preset_name),
    ),

    # ── History ──────────────────────────────────────────────────────────────
    ToolSpec(
        name="undo",
        description="Undo the last mutating action.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.history.undo(),
    ),
    ToolSpec(
        name="redo",
        description="Redo the last undone action.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.history.redo(),
    ),
    ToolSpec(
        name="list_history",
        description="List the undo/redo command history as plain-English labels.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.history.history(),
        mutates=False,
    ),

    # ── Project info ─────────────────────────────────────────────────────────
    ToolSpec(
        name="project_info",
        description="Human-readable summary of the active project (CHID, entity counts, T_END).",
        input_schema={"type": "object", "properties": {}},
        handler=lambda api: api.info(),
        mutates=False,
    ),
]
