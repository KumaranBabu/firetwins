"""Rename one or many objects, optionally from a name template: ``api.rename`` (PyroSim "Bulk Renaming").

A template mixes text with ``${keyword}`` parts that are worked out for each object::

    ${base_name}${type}_${post_num}     Exterior56 (a door)  ->  ExteriorDoor_56

Keywords: name, base_name (name without leading and trailing digits), parent_name (its group; ``parent_name-2`` the group above),
pre_num, post_num (the digits at the start and end of the name), sel_index (1-based place in the selection), global_index
(1-based place among objects of its type), local_index (1-based place in its group), results_id (empty: PyFDS has no results
id), type. Names stay unique within a kind of object (a clash gets " 2", " 3" ...), and every use of a renamed object by
another (``SURF_ID``, ``CTRL_ID`` ...) follows it, all in one undo step.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

KEYWORDS = ("name", "base_name", "parent_name", "parent_name-1", "pre_num", "post_num", "sel_index", "global_index",
            "local_index", "results_id", "type")
_TOKEN = re.compile(r"\$\{([A-Za-z_]+(?:-\d+)?)\}")
_DESCRIPTIONS = {
    "name": "The existing name of the object.",
    "base_name": "The existing name without any leading or trailing numbers.",
    "parent_name": "The name of the group the object is in (parent_name-2 goes one level up).",
    "pre_num": "Any number at the beginning of the existing name.",
    "post_num": "Any number at the end of the existing name.",
    "sel_index": "The 1-based index of the object in the current selection.",
    "global_index": "The 1-based index of the object among all objects of its type.",
    "local_index": "The 1-based index of the object within its group.",
    "results_id": "The results id of the object, when there is one (always empty here).",
    "type": "The object type.",
}


def describe(keyword: str) -> str:
    return _DESCRIPTIONS.get(keyword.split("-")[0] if keyword.startswith("parent_name") else keyword, "")


class RenameManager:
    def __init__(self, api) -> None:
        self._api = api

    # -- the template ---------------------------------------------------------------------------------------------
    def expand(self, template: str, entity: Any, sel_index: int = 1) -> str:
        """The name *template* gives *entity* (not yet made unique)."""
        values = self._values(entity, sel_index)

        def one(m: "re.Match[str]") -> str:
            key = m.group(1)
            if key.startswith("parent_name-"):
                return self._ancestor(entity, int(key.split("-")[1]))
            if key not in values:
                raise ValueError(f"unknown keyword ${{{key}}}; use one of: " + ", ".join(f"${{{k}}}" for k in KEYWORDS))
            return values[key]
        return _TOKEN.sub(one, template)

    def _values(self, entity: Any, sel_index: int) -> Dict[str, str]:
        name = str(getattr(entity, "name", "") or "")
        pre = re.match(r"\d+", name)
        post = re.search(r"\d+$", name)
        base = name[len(pre.group(0)) if pre else 0:len(name) - (len(post.group(0)) if post and not (pre and pre.group(0) == name) else 0)]
        coll = self._api.dependencies.collection_of(entity)
        peers = getattr(self._api, coll).all() if coll else []
        group = self._api.groups.group_of(entity)
        siblings = self._api.groups.members(group) if group else peers
        return {
            "name": name, "base_name": base, "parent_name": group or "",
            "pre_num": pre.group(0) if pre else "", "post_num": post.group(0) if post and not (pre and pre.group(0) == name) else "",
            "sel_index": str(sel_index),
            "global_index": str(next((i + 1 for i, e in enumerate(peers) if e is entity), 0)),
            "local_index": str(next((i + 1 for i, e in enumerate(siblings) if e is entity), 0)),
            "results_id": "", "type": type(entity).__name__,
        }

    def _ancestor(self, entity: Any, levels: int) -> str:
        """Groups have no parents in PyFDS (they are flat), so only the first level has a name."""
        return (self._api.groups.group_of(entity) or "") if levels <= 1 else ""

    # -- preview and apply ----------------------------------------------------------------------------------------
    def preview(self, entities: Sequence[Any], template: Optional[str] = None, name: Optional[str] = None) -> List[Tuple[Any, str]]:
        """``[(entity, new name)]`` for the selection: *template* is worked out per object; *name* is given to all of them
        (a clash gets a number). Raises ValueError for an empty or unknown template."""
        if (template is None) == (name is None):
            raise ValueError("give either a template or a name")
        text = template if template is not None else name
        if not text.strip():
            raise ValueError("a name cannot be empty")
        taken: Dict[str, set] = {}
        out: List[Tuple[Any, str]] = []
        selected = {id(e) for e in entities}
        for i, e in enumerate(entities, start=1):
            coll = self._api.dependencies.collection_of(e)
            if coll not in taken:                                   # names of the objects that are NOT being renamed
                taken[coll] = {x.name for x in getattr(self._api, coll).all() if id(x) not in selected}
            new = self.expand(text, e, i) if template is not None else text
            if not new.strip():
                raise ValueError(f"the template gives {getattr(e, 'name', e)!r} an empty name")
            final, n = new, 1
            while final in taken[coll]:
                n += 1
                final = f"{new} {n}"
            taken[coll].add(final)
            out.append((e, final))
        return out

    def rename(self, entities: Sequence[Any], template: Optional[str] = None, name: Optional[str] = None) -> int:
        """Rename the objects (one undo step) and repoint everything that used the old names. Returns how many changed."""
        plan = [(e, new) for e, new in self.preview(entities, template, name) if new != e.name]
        if not plan:
            return 0
        uses = {id(e): self._api.dependencies.dependents(e) for e, _ in plan}
        olds = {id(e): e.name for e, _ in plan}
        with self._api.history.transaction(f"rename {len(plan)} object(s)"):
            for e, new in plan:
                self._api.set_property(e, "name", new)
            for e, new in plan:
                for other, field in uses[id(e)]:
                    self._api.set_property(other, field, self._api.dependencies._swap(getattr(other, field), olds[id(e)], new))
        return len(plan)
