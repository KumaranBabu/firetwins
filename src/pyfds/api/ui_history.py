"""Selection and view history: ``api.ui_history`` (UX-02).

PyroSim has *Undo* (every step, selection and view changes included) and *Undo Edit* (model edits
only). ``api.history`` is the model history, i.e. *Undo Edit*. This is the other stack: it records
selection, section-box, active-view and hidden-type changes so a user can step back through them.
The two stacks are separate; they are not merged into one chronological order.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

MAX_DEPTH = 200


class UiHistory:
    def __init__(self, api) -> None:
        self._api = api
        self._undo: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
        self._redo: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
        self._suspend = False
        self._last: Dict[str, Any] = {}
        self._attached = None
        self.attach()

    def attach(self) -> None:
        """(Re)bind to the API's current selection manager and project; clears the history."""
        sel = self._api.selection
        if self._attached is not sel:
            self._attached = sel
            sel.observers.append(lambda: self.record("selection"))
        self._undo.clear()
        self._redo.clear()
        self._last = self._capture()

    def _capture(self) -> Dict[str, Any]:
        ed = self._api.project.editor
        return {"selection": frozenset(e.uid for e in self._api.selection.selected),
                "section_box": ed.section_box.to_dict() if ed.section_box else None,
                "active_view": ed.active_view,
                "hidden_types": frozenset(ed.hidden_types)}

    def record(self, label: str) -> None:
        if self._suspend:
            return
        now = self._capture()
        if now == self._last:
            return
        self._undo.append((label, self._last, now))
        del self._undo[:-MAX_DEPTH]
        self._redo.clear()
        self._last = now

    def _apply(self, state: Dict[str, Any]) -> None:
        from pyfds.core.selection import SelectionMode
        from pyfds.domain.views import SectionBox
        api, ed = self._api, self._api.project.editor
        self._suspend = True
        try:
            by_uid = {e.uid: e for e in api.project.all_entities}
            api.selection.select_many([by_uid[u] for u in state["selection"] if u in by_uid], SelectionMode.REPLACE)
            ed.section_box = SectionBox.from_dict(state["section_box"]) if state["section_box"] else None
            ed.active_view = state["active_view"] if state["active_view"] in ed.views else None
            ed.hidden_types = set(state["hidden_types"])
        finally:
            self._suspend = False
        self._last = self._capture()
        api.project.notify_global("VIEWS_CHANGED", None)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> Optional[str]:
        """Step back one selection/view change; returns its label, or None if there is nothing to undo."""
        if not self._undo:
            return None
        label, before, after = self._undo.pop()
        self._apply(before)
        self._redo.append((label, before, after))
        return label

    def redo(self) -> Optional[str]:
        if not self._redo:
            return None
        label, before, after = self._redo.pop()
        self._apply(after)
        self._undo.append((label, before, after))
        return label

    def labels(self) -> List[str]:
        return [l for l, _, _ in self._undo]

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._last = self._capture()
