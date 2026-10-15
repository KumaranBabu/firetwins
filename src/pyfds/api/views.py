"""Saved views and the section box: ``api.views`` (UX-06, UX-07, RES-12).

View state, like ``api.view``: saved in the ``.pyfds`` file, never written to FDS. Changes are not
in the model's undo history; they are recorded in ``api.ui_history`` ("Undo" vs "Undo Edit").
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from pyfds.domain.views import SavedView, SectionBox


def _xb(entity: Any) -> Optional[List[float]]:
    try:
        return [entity.x_min, entity.x_max, entity.y_min, entity.y_max, entity.z_min, entity.z_max]
    except AttributeError:
        return None


class ViewsManager:
    def __init__(self, api) -> None:
        self._api = api

    @property
    def _ed(self):
        return self._api.project.editor

    def _changed(self, label: str) -> None:
        self._api.ui_history.record(label)
        self._api.project.notify_global("VIEWS_CHANGED", None)

    # -- saved views -----------------------------------------------------------------
    def all(self) -> List[SavedView]:
        return list(self._ed.views.values())

    def get(self, name: str) -> Optional[SavedView]:
        return self._ed.views.get(name)

    @property
    def active(self) -> Optional[str]:
        return self._ed.active_view

    def _require(self, name: str) -> SavedView:
        v = self._ed.views.get(name)
        if v is None:
            raise KeyError(f"view {name!r} not found")
        return v

    def _snapshot(self, name: str, description: str) -> SavedView:
        box = self._ed.section_box
        return SavedView(name=name, description=description,
                         camera=self._api.viewport.state.camera.to_dict(),
                         section_box=box.to_dict() if box else None,
                         hidden_types=sorted(self._ed.hidden_types))

    def save_viewpoint(self, name: str, description: str = "") -> SavedView:
        """Store the current camera, section box and hidden types under *name* (replaces a view of that name)."""
        if not name.strip():
            raise ValueError("a view needs a name")
        view = self._snapshot(name, description)
        self._ed.views[name] = view
        self._ed.active_view = name
        self._changed(f"save view {name}")
        return view

    def new_view(self, name: str, description: str = "") -> SavedView:
        """A new view (PyroSim 'New View'): the current state, under an unused name."""
        if name in self._ed.views:
            raise ValueError(f"view {name!r} already exists")
        return self.save_viewpoint(name, description)

    def reset_to(self, name: str) -> SavedView:
        """Apply a saved view: camera, section box and hidden types; it becomes the active view."""
        from pyfds.core.viewport_camera import ViewportCamera
        from pyfds.core.viewport_types import ProjectionMode
        view = self._require(name)
        if view.camera:
            c = dict(view.camera)
            c["projection"] = ProjectionMode[c.get("projection", "PERSPECTIVE")]
            for k in ("position", "target", "up"):
                c[k] = tuple(c[k])
            self._api.viewport.set_camera(ViewportCamera(**c))
        self._ed.section_box = SectionBox.from_dict(view.section_box) if view.section_box else None
        self._ed.hidden_types = set(view.hidden_types)
        self._ed.active_view = name
        self._changed(f"go to view {name}")
        return view

    def set_active(self, name: str) -> None:
        self._require(name)
        if self._ed.active_view != name:
            self._ed.active_view = name
            self._changed(f"activate view {name}")

    def duplicate(self, name: str, new_name: str) -> SavedView:
        src = self._require(name)
        if new_name in self._ed.views:
            raise ValueError(f"view {new_name!r} already exists")
        dup = SavedView.from_dict({**src.to_dict(), "name": new_name})
        self._ed.views[new_name] = dup
        self._changed(f"duplicate view {name}")
        return dup

    def rename(self, name: str, new_name: str) -> SavedView:
        view = self._require(name)
        if new_name in self._ed.views:
            raise ValueError(f"view {new_name!r} already exists")
        del self._ed.views[name]
        view.name = new_name
        self._ed.views[new_name] = view
        if self._ed.active_view == name:
            self._ed.active_view = new_name
        self._changed(f"rename view {name}")
        return view

    def delete(self, name: str) -> None:
        self._require(name)
        del self._ed.views[name]
        if self._ed.active_view == name:
            self._ed.active_view = None
        self._changed(f"delete view {name}")

    # -- section box -------------------------------------------------------------------
    def section_box(self) -> Optional[SectionBox]:
        return self._ed.section_box

    def set_section_box(self, x_min=None, x_max=None, y_min=None, y_max=None, z_min=None, z_max=None,
                        enabled: bool = True, visible: bool = True) -> SectionBox:
        """Set the clipping box; a side left out is open. Replaces any current box."""
        box = SectionBox(x_min, x_max, y_min, y_max, z_min, z_max, enabled, visible)
        box.validate()
        self._ed.section_box = box
        self._changed("set section box")
        return box

    def fit_section_box(self, entities: Iterable[Any], margin: float = 0.0) -> SectionBox:
        """A box around the given objects (those with x/y/z bounds), grown by *margin* metres."""
        boxes = [b for b in (_xb(e) for e in entities) if b]
        if not boxes:
            raise ValueError("none of the given objects has a position")
        lo = [min(b[2 * i] for b in boxes) - margin for i in range(3)]
        hi = [max(b[2 * i + 1] for b in boxes) + margin for i in range(3)]
        return self.set_section_box(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])

    def set_section_enabled(self, enabled: bool) -> None:
        box = self._require_box()
        box.enabled = bool(enabled)
        self._changed("enable section box" if enabled else "disable section box")

    def set_section_visible(self, visible: bool) -> None:
        box = self._require_box()
        box.visible = bool(visible)
        self._changed("show section box" if visible else "hide section box")

    def reset_section_box(self) -> None:
        """Remove the box (everything is shown again)."""
        if self._ed.section_box is not None:
            self._ed.section_box = None
            self._changed("reset section box")

    def _require_box(self) -> SectionBox:
        if self._ed.section_box is None:
            raise ValueError("there is no section box; set one first")
        return self._ed.section_box

    def clip_planes(self):
        box = self._ed.section_box
        return box.clip_planes() if box else []

    def clipped_out(self, entities: Optional[Iterable[Any]] = None) -> List[Any]:
        """Objects entirely outside the section box (a renderer need not draw them)."""
        box = self._ed.section_box
        if box is None or not box.enabled:
            return []
        if entities is None:
            entities = [e for attr in sorted(set(self._api.project._TYPE_MAP.values()))
                        for e in getattr(self._api.project, attr)]
        return [e for e in entities if (xb := _xb(e)) is not None and not box.intersects(xb)]
