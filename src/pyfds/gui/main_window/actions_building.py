"""Draw menu: Floor, Ceiling, Stair, Door, Window, Beam, Pipe, Ramp (plan step F1). Each opens a small form with sensible
defaults taken from the model, then calls ``api.geom``; pass *values* to skip the form."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PySide6.QtWidgets import QDialog, QMessageBox

from pyfds.gui.entity_dialogs import SchemaFormDialog


def _vec(default: List[float], note: str) -> Dict[str, Any]:
    return {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "default": default,
            "description": note}


def _num(default: float, note: str = "") -> Dict[str, Any]:
    return {"type": "number", "default": default, "description": note}


def _text(default: str) -> Dict[str, Any]:
    return {"type": "string", "default": default}


class ActionsBuildingMixin:
    def _model_rect(self) -> List[float]:
        """x0, x1, y0, y1 of the first mesh (the room a floor or ceiling usually spans), else a 5 x 5 m square."""
        meshes = self.api.meshes.all()
        if meshes:
            m = meshes[0]
            return [m.x_min, m.x_max, m.y_min, m.y_max]
        return [0.0, 5.0, 0.0, 5.0]

    def _element_forms(self) -> Dict[str, Dict[str, Any]]:
        x0, x1, y0, y1 = self._model_rect()
        centre = [(x0 + x1) / 2, (y0 + y1) / 2, 0.0]
        return {
            "floor": {"title": "Draw Floor", "props": {
                "name": _text("FLOOR"), "x_min": _num(x0), "x_max": _num(x1), "y_min": _num(y0), "y_max": _num(y1),
                "z_top": _num(0.0, "Height of the top surface (m)"), "thickness": _num(0.2, "m, extends downwards"),
                "surf_id": _text("INERT")}},
            "ceiling": {"title": "Draw Ceiling", "props": {
                "name": _text("CEILING"), "x_min": _num(x0), "x_max": _num(x1), "y_min": _num(y0), "y_max": _num(y1),
                "z_top": _num(3.0, "Height of the top surface (m)"), "thickness": _num(0.2, "m, extends downwards"),
                "surf_id": _text("INERT")}},
            "door": {"title": "Draw Door", "props": {
                "name": _text("DOOR"), "centre": _vec(centre, "Middle of the door in plan, and the floor level (x, y, z)"),
                "wall_axis": {"type": "string", "enum": ["X", "Y"], "default": "X",
                              "description": "Direction the wall runs"},
                "width": _num(0.9), "height": _num(2.1), "sill": _num(0.0, "Height above the floor (m)"),
                "wall_thickness": _num(0.3, "Depth of the cut: a little more than the wall (m)")}},
            "window": {"title": "Draw Window", "props": {
                "name": _text("WINDOW"), "centre": _vec(centre, "Middle of the window in plan, and the floor level (x, y, z)"),
                "wall_axis": {"type": "string", "enum": ["X", "Y"], "default": "X",
                              "description": "Direction the wall runs"},
                "width": _num(1.2), "height": _num(1.2), "sill": _num(0.9, "Height above the floor (m)"),
                "wall_thickness": _num(0.3, "Depth of the cut: a little more than the wall (m)")}},
            "beam": {"title": "Draw Beam", "props": {
                "name": _text("BEAM"), "start": _vec([x0, centre[1], 3.0], "One end (x, y, z)"),
                "end": _vec([x1, centre[1], 3.0], "Other end: differs from the start in exactly one coordinate"),
                "width": _num(0.2), "depth": _num(0.3), "surf_id": _text("INERT")}},
            "pipe": {"title": "Draw Pipe", "props": {
                "name": _text("PIPE"), "start": _vec([centre[0], centre[1], 0.0], "One end (x, y, z)"),
                "end": _vec([centre[0], centre[1], 3.0], "Other end (any direction)"),
                "outer_radius": _num(0.15), "wall": _num(0.02, "Wall thickness (a solid rod if at least the radius)"),
                "surf_id": _text("INERT")}},
            "ramp": {"title": "Draw Ramp", "props": {
                "name": _text("RAMP"), "origin": _vec([x0, y0, 0.0], "Where the low edge starts (x, y, z)"),
                "direction": {"type": "string", "enum": ["+X", "-X", "+Y", "-Y"], "default": "+X",
                              "description": "Direction the ramp climbs"},
                "length": _num(3.0), "width": _num(1.2, "To the left of the climbing direction"),
                "rise": _num(0.5, "Total height gained (m)"), "surf_id": _text("INERT")}},
        }

    def _build_element(self, kind: str, v: Dict[str, Any]) -> Any:
        g = self.api.geom
        if kind in ("floor", "ceiling"):
            poly = [(v["x_min"], v["y_min"]), (v["x_max"], v["y_min"]), (v["x_max"], v["y_max"]), (v["x_min"], v["y_max"])]
            if v["x_max"] <= v["x_min"] or v["y_max"] <= v["y_min"]:
                raise ValueError("the maximum must be larger than the minimum in both X and Y")
            return g.add_slab(poly, v["z_top"], v["thickness"], surf_id=v.get("surf_id") or "INERT", name=v["name"])
        if kind in ("door", "window"):
            return g.add_opening(kind, v["centre"], v["wall_axis"], v["width"], v["height"], v["sill"],
                                 v["wall_thickness"], v["name"])
        if kind == "beam":
            return g.add_beam(v["start"], v["end"], v["width"], v["depth"], v.get("surf_id") or "INERT", v["name"])
        if kind == "pipe":
            return g.add_pipe(v["start"], v["end"], v["outer_radius"], v["wall"], v.get("surf_id") or "INERT", v["name"])
        if kind == "ramp":
            return g.add_sloped_ramp(v["origin"], v["direction"], v["length"], v["width"], v["rise"],
                                     v.get("surf_id") or "INERT", v["name"])
        raise ValueError(f"unknown building element {kind!r}")

    def _draw_element(self, kind: str, values: Optional[Dict[str, Any]] = None) -> Any:
        """Ask for the element's size (unless *values* are given) and add it. Returns what was made, or None."""
        form = self._element_forms()[kind]
        if values is None:
            schema = {"type": "object", "properties": form["props"], "required": [k for k in form["props"] if k != "surf_id"]}
            dialog = SchemaFormDialog(form["title"], "", schema, self)
            if dialog.exec() != QDialog.Accepted:
                return None
            values = dialog.values()
        merged = {k: p["default"] for k, p in form["props"].items()}
        merged.update({k: v for k, v in values.items() if v is not None})
        try:
            made = self._build_element(kind, merged)
        except (ValueError, KeyError) as exc:
            QMessageBox.critical(self, f"Could not draw {kind}", str(exc))
            return None
        self.explorer.refresh()
        return made

    def _on_draw_floor(self) -> Any:
        return self._draw_element("floor")

    def _on_draw_ceiling(self) -> Any:
        return self._draw_element("ceiling")

    def _on_draw_stair(self) -> None:
        self._on_add_entity("add_stairs")

    def _on_draw_door(self) -> Any:
        return self._draw_element("door")

    def _on_draw_window(self) -> Any:
        return self._draw_element("window")

    def _on_draw_beam(self) -> Any:
        return self._draw_element("beam")

    def _on_draw_pipe(self) -> Any:
        return self._draw_element("pipe")

    def _on_draw_ramp(self) -> Any:
        return self._draw_element("ramp")
