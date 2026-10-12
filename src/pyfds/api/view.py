"""Object visibility: ``api.view`` (UX-08).

Hide / show / isolate / filter individual objects and switch whole entity types on or off. This is
view state: it is saved in the ``.pyfds`` file with the document, never written to the FDS file, and
is not part of undo history (hiding something is not an edit of the model).
"""
from __future__ import annotations

from typing import Any, Iterable, List, Optional


class VisibilityManager:
    def __init__(self, api) -> None:
        self._api = api

    @property
    def _ed(self):
        return self._api.project.editor

    def _collections(self):
        p = self._api.project
        return {attr: getattr(p, attr) for attr in sorted(set(p._TYPE_MAP.values()))}

    def _changed(self) -> None:
        self._api.project.notify_global("VISIBILITY_CHANGED", None)

    def _resolve(self, items) -> List[Any]:
        if items is None:
            return []
        if not isinstance(items, (list, tuple, set)):
            items = [items]
        known = {e.uid: e for c in self._collections().values() for e in c}
        out = []
        for it in items:
            uid = getattr(it, "uid", None)
            if uid not in known:
                raise KeyError(f"{getattr(it, 'name', it)!r} is not in the project")
            out.append(known[uid])
        return out

    # -- single objects --------------------------------------------------------------
    def hide(self, entities) -> int:
        """Hide these objects; returns how many changed."""
        items = [e for e in self._resolve(entities) if e.uid not in self._ed.hidden]
        self._ed.hidden.update(e.uid for e in items)
        if items:
            self._changed()
        return len(items)

    def show(self, entities) -> int:
        items = [e for e in self._resolve(entities) if e.uid in self._ed.hidden]
        self._ed.hidden.difference_update(e.uid for e in items)
        if items:
            self._changed()
        return len(items)

    def show_all(self) -> None:
        """Show every object and switch every type back on."""
        if self._ed.hidden or self._ed.hidden_types:
            self._ed.hidden.clear()
            self._ed.hidden_types.clear()
            self._changed()

    def isolate(self, entities) -> int:
        """Hide everything except *entities* (which are shown); returns the number of hidden objects."""
        keep = {e.uid for e in self._resolve(entities)}
        if not keep:
            raise ValueError("isolate needs at least one object")
        everything = [e for c in self._collections().values() for e in c]
        self._ed.hidden = {e.uid for e in everything if e.uid not in keep}
        self._changed()
        return len(self._ed.hidden)

    def filter(self, collection: Optional[str] = None, name_contains: Optional[str] = None,
               tag: Optional[str] = None, surface: Optional[str] = None) -> int:
        """Show only objects matching ALL given criteria and hide the rest; returns the number shown."""
        if not any((collection, name_contains, tag, surface)):
            raise ValueError("give at least one criterion")
        cols = self._collections()
        if collection is not None and collection not in cols:
            raise KeyError(f"unknown collection {collection!r}")

        def ok(attr, e):
            if collection and attr != collection:
                return False
            if name_contains and name_contains.lower() not in str(getattr(e, "name", "")).lower():
                return False
            if tag and tag not in (e.tags or []):
                return False
            if surface and getattr(e, "surface_id", None) != surface:
                return False
            return True

        shown = {e.uid for attr, c in cols.items() for e in c if ok(attr, e)}
        self._ed.hidden = {e.uid for c in cols.values() for e in c if e.uid not in shown}
        self._changed()
        return len(shown)

    # -- whole types -----------------------------------------------------------------
    def set_type_visible(self, collection: str, visible: bool) -> None:
        if collection not in self._collections():
            raise KeyError(f"unknown collection {collection!r}; e.g. 'obstructions', 'vents', 'devices'")
        before = set(self._ed.hidden_types)
        (self._ed.hidden_types.discard if visible else self._ed.hidden_types.add)(collection)
        if before != self._ed.hidden_types:
            self._changed()

    def hidden_types(self) -> List[str]:
        return sorted(self._ed.hidden_types)

    # -- queries ---------------------------------------------------------------------
    def is_visible(self, entity) -> bool:
        if entity.uid in self._ed.hidden:
            return False
        attr = next((a for a, c in self._collections().items() if any(x is entity for x in c)), None)
        return attr not in self._ed.hidden_types

    def hidden(self) -> List[Any]:
        return [e for c in self._collections().values() for e in c if e.uid in self._ed.hidden]

    def visible(self, collection: str) -> List[Any]:
        cols = self._collections()
        if collection not in cols:
            raise KeyError(f"unknown collection {collection!r}")
        if collection in self._ed.hidden_types:
            return []
        return [e for e in cols[collection] if e.uid not in self._ed.hidden]
