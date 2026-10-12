"""Move / Rotate / Scale / Mirror Selected and snap settings."""
from __future__ import annotations

import math
from typing import Any, List

from PySide6.QtWidgets import QDialog, QMessageBox

from pyfds.automation.commands import (
    GroupCommand,
    MirrorCommand,
    MirrorGeomCommand,
    MoveObstCommand,
    RotateCommand,
    RotateGeomCommand,
    ScaleCommand,
    ScaleGeomCommand,
    TranslateGeomCommand,
    TranslatePointCommand,
)
from pyfds.gui.entity_dialogs import SchemaFormDialog

from .selection import (
    _point_xyz,
    _selection_bbox,
    _transform_kind,
)


class ActionsTransformMixin:
    def _resolve_transform_targets(self) -> List[Any]:
        """Selected entities, expanded so selecting one grouped entity pulls
        in its whole group as one rigid transform target — this is what
        makes Group/Ungroup useful for Move/Rotate/Scale/Mirror, not just
        an Explorer-tree decoration."""
        resolved: List[Any] = []
        seen = set()
        for _, entity in self.explorer.selected_entities():
            group_name = self.api.groups.group_of(entity)
            members = self.api.groups.members(group_name) if group_name else [entity]
            for member in members:
                key = id(member)
                if key not in seen:
                    seen.add(key)
                    resolved.append(member)
        return resolved

    def _apply_transform(self, entities: List[Any], title: str, build_command_for) -> None:
        """Shared plumbing for Move/Rotate/Scale/Mirror Selected:
        build_command_for(kind, entity, bbox) returns a Command (or None to
        skip that entity) — one command per transformable entity, executed
        as a single GroupCommand so the whole multi-entity operation is one
        undo step. An entity whose command constructor rejects the given
        parameters (e.g. RotateCommand's XB entities only accept multiples
        of 90°) is skipped rather than aborting the whole batch."""
        bbox = _selection_bbox(entities)
        commands = []
        skipped = 0
        for entity in entities:
            kind = _transform_kind(entity)
            if kind is None:
                skipped += 1
                continue
            try:
                cmd = build_command_for(kind, entity, bbox)
            except Exception:
                cmd = None
            if cmd is not None:
                commands.append(cmd)
            else:
                skipped += 1
        if not commands:
            QMessageBox.information(self, title, "Nothing in the selection can be transformed.")
            return
        try:
            self.api.history.execute(GroupCommand(commands, label=title))
        except Exception as exc:
            QMessageBox.critical(self, f"Could not {title.lower()}", str(exc))
            return
        suffix = f" ({skipped} skipped)" if skipped else ""
        self.statusBar().showMessage(f"{title}: {len(commands)} object(s) transformed{suffix}.")

    def _on_move_selected(self) -> None:
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, "Move Selected", "Nothing selected.")
            return
        schema = {
            "type": "object",
            "properties": {
                "dx": {"type": "number", "default": 0.0},
                "dy": {"type": "number", "default": 0.0},
                "dz": {"type": "number", "default": 0.0},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Move Selected", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        dx, dy, dz = values.get("dx", 0.0), values.get("dy", 0.0), values.get("dz", 0.0)

        def build(kind, entity, bbox):
            if kind == "xb":
                return MoveObstCommand(entity, dx=dx, dy=dy, dz=dz)
            if kind == "geom":
                return TranslateGeomCommand(entity, dx=dx, dy=dy, dz=dz)
            if kind == "point":
                return TranslatePointCommand(entity, dx=dx, dy=dy, dz=dz)
            return None

        self._apply_transform(entities, "Move Selected", build)

    def _on_rotate_selected(self) -> None:
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, "Rotate Selected", "Nothing selected.")
            return
        schema = {
            "type": "object",
            "properties": {
                "degrees": {"type": "number", "default": 90.0,
                            "description": "About Z, shared pivot. XB entities "
                                           "(Obstruction/Mesh/Vent/Hole) only "
                                           "accept multiples of 90."},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Rotate Selected", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        degrees = dialog.values().get("degrees", 90.0)

        def build(kind, entity, bbox):
            ox, oy = (bbox[0] + bbox[1]) / 2, (bbox[2] + bbox[3]) / 2
            if kind == "xb":
                return RotateCommand(entity, degrees=degrees, origin=(ox, oy))
            if kind == "geom":
                return RotateGeomCommand(entity, degrees=degrees, origin=(ox, oy))
            if kind == "point":
                x, y, z = _point_xyz(entity)
                rad = math.radians(degrees)
                dxr, dyr = x - ox, y - oy
                nx = ox + dxr * math.cos(rad) - dyr * math.sin(rad)
                ny = oy + dxr * math.sin(rad) + dyr * math.cos(rad)
                return TranslatePointCommand(entity, dx=nx - x, dy=ny - y, dz=0.0)
            return None

        self._apply_transform(entities, "Rotate Selected", build)

    def _on_scale_selected(self) -> None:
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, "Scale Selected", "Nothing selected.")
            return
        schema = {
            "type": "object",
            "properties": {
                "factor": {"type": "number", "default": 1.0,
                           "description": "Uniform scale about the selection's shared centroid."},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Scale Selected", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        factor = dialog.values().get("factor", 1.0)

        def build(kind, entity, bbox):
            origin = ((bbox[0] + bbox[1]) / 2, (bbox[2] + bbox[3]) / 2, (bbox[4] + bbox[5]) / 2)
            if kind == "xb":
                return ScaleCommand(entity, factor=factor, origin=origin)
            if kind == "geom":
                return ScaleGeomCommand(entity, factor=factor, origin=origin)
            if kind == "point":
                x, y, z = _point_xyz(entity)
                ox, oy, oz = origin
                nx, ny, nz = ox + (x - ox) * factor, oy + (y - oy) * factor, oz + (z - oz) * factor
                return TranslatePointCommand(entity, dx=nx - x, dy=ny - y, dz=nz - z)
            return None

        self._apply_transform(entities, "Scale Selected", build)

    def _on_mirror_selected(self) -> None:
        entities = self._resolve_transform_targets()
        if not entities:
            QMessageBox.information(self, "Mirror Selected", "Nothing selected.")
            return
        schema = {
            "type": "object",
            "properties": {
                "axis": {"type": "string", "enum": ["X", "Y", "Z"], "default": "X"},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Mirror Selected", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        axis_idx = {"X": 0, "Y": 1, "Z": 2}[dialog.values().get("axis", "X")]

        def build(kind, entity, bbox):
            lo, hi = bbox[axis_idx * 2], bbox[axis_idx * 2 + 1]
            position = (lo + hi) / 2
            if kind == "xb":
                return MirrorCommand(entity, axis=axis_idx, position=position)
            if kind == "geom":
                return MirrorGeomCommand(entity, axis=axis_idx, position=position)
            if kind == "point":
                coords = list(_point_xyz(entity))
                old = coords[axis_idx]
                coords[axis_idx] = 2 * position - old
                nx, ny, nz = coords
                x, y, z = _point_xyz(entity)
                return TranslatePointCommand(entity, dx=nx - x, dy=ny - y, dz=nz - z)
            return None

        self._apply_transform(entities, "Mirror Selected", build)

    def _on_snap_settings(self) -> None:
        snap = self.api.viewport.state.snap
        schema = {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": snap.enabled},
                "grid_size": {"type": "number", "default": snap.grid_size, "description": "Metres per grid division."},
                "angle_step_deg": {"type": "number", "default": snap.angle_step_deg},
                "snap_to_grid": {"type": "boolean", "default": snap.snap_to_grid},
                "snap_to_vertex": {"type": "boolean", "default": snap.snap_to_vertex},
                "snap_to_edge": {"type": "boolean", "default": snap.snap_to_edge},
                "snap_to_face": {"type": "boolean", "default": snap.snap_to_face},
            },
            "required": [],
        }
        dialog = SchemaFormDialog("Snap Settings", "", schema, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.api.viewport.set_snap(**dialog.values())
