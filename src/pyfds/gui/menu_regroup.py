"""Regrouping finished menus: move existing entries (found by their text) into a new submenu, in place.

Menus are built by many mixins and plugins; long flat lists are folded into submenus once everything is there,
so every entry keeps its handler, shortcut and tip. Used by both windows (see ``MAIN_GROUPS`` / ``RESULTS_GROUPS``).
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMenuBar

#: (menu path, new submenu title, entries by text start, options). A menu path is "Top" or "Top/Sub". Options:
#: ``anywhere`` - also take the entries from other menus; ``after`` - put the submenu after this entry
#: (default: where the first moved entry was).
Group = Tuple[str, str, Sequence[str], Dict[str, object]]

MAIN_GROUPS: List[Group] = [
    ("Edit", "&Visibility", ["Hide Selected", "Show Selected", "Filter (Show Only Selection)", "Show All"], {}),
    ("Edit", "&Transform", ["Move Selected", "Rotate Selected", "Scale Selected", "Mirror Selected", "Snap Settings"],
     {}),
    ("Model", "Add from &Library", ["Add Surface (Library)", "Add Fuel Reaction (Library)", "Add Material (Library)"],
     {}),
    ("Model", "Add &Special", ["Add Typed Surface", "Add Complex Stoichiometry Reaction", "Add Liquid Fuel"], {}),
    # every "check my model" command in one place, beside Validate Project (some used to be under Tools)
    ("Model", "Model &Checks", ["Run Model Checks", "Edit Model Checks", "Validation", "Find Errors",
                                "Mesh Diagnostics", "Mesh Checker"], {"anywhere": True, "after": "Auto-Fix"}),
    ("View", "&Rendering Mode", ["Wireframe Mode", "Shaded Mode", "Outlines Mode", "Realistic Mode"], {}),
]

RESULTS_GROUPS: List[Group] = [
    ("File", "&Movie", ["Save Movie", "Save 360 Movie", "Record Movie", "Pause / Resume Recording", "Stop Recording"],
     {}),
    ("View", "Section &Box", ["Add Section Box", "Remove Section Box", "Set Section Plane"], {}),
    ("View", "&Units", ["Time Display", "Temperature Unit", "Concentration Unit", "Mass Fraction Unit"], {}),
]


def _plain(action: QAction) -> str:
    return action.text().replace("&&", "\0").replace("&", "").replace("\0", "&").split("\t")[0]


def _menu_at(bar: QMenuBar, path: str) -> Optional[QMenu]:
    menu: Optional[QMenu] = None
    for part in path.split("/"):
        actions = (menu.actions() if menu else bar.actions())
        menu = next((a.menu() for a in actions if a.menu() is not None and _plain(a) == part), None)
        if menu is None:
            return None
    return menu


def _all_menus(bar: QMenuBar) -> Iterable[QMenu]:
    stack = [a.menu() for a in bar.actions() if a.menu() is not None]
    while stack:
        m = stack.pop()
        yield m
        stack.extend(a.menu() for a in m.actions() if a.menu() is not None)


def _tidy_separators(menu: QMenu) -> None:
    """No separator at either end and never two in a row (moving entries out can leave them behind)."""
    prev_sep = True
    acts = menu.actions()
    for a in acts:
        if a.isSeparator():
            if prev_sep:
                menu.removeAction(a)
            prev_sep = True
        else:
            prev_sep = False
    acts = menu.actions()
    while acts and acts[-1].isSeparator():
        menu.removeAction(acts.pop())


def regroup(bar: QMenuBar, groups: Sequence[Group]) -> Dict[str, QMenu]:
    """Fold the listed entries (commands or whole submenus) into new submenus. Entries are looked for in the target
    menu, and with ``anywhere`` in the rest of the menu bar too (so a command can move from Tools into Model).
    Missing entries are skipped; a submenu that would stay empty is not made. Returns the new submenus by title."""
    made: Dict[str, QMenu] = {}
    for path, title, starts, opts in groups:
        target = _menu_at(bar, path)
        if target is None:
            continue
        found: List[Tuple[QMenu, QAction]] = []
        for start in starts:
            match = lambda a: not a.isSeparator() and _plain(a).startswith(start)      # noqa: E731
            hit = next(((target, a) for a in target.actions() if match(a)), None)
            if hit is None and opts.get("anywhere"):
                hit = next(((m, a) for m in _all_menus(bar) if m is not target for a in m.actions()
                            if match(a) and a.menu() is None), None)
            if hit is not None and hit[1] not in [x for _, x in found]:
                found.append(hit)
        if not found:
            continue
        sub = QMenu(title, target)
        after = opts.get("after")
        acts = target.actions()
        if after:
            i = next((k for k, a in enumerate(acts) if _plain(a).startswith(str(after))), None)
            anchor = acts[i + 1] if i is not None and i + 1 < len(acts) else None
        else:
            own = [a for m, a in found if m is target]
            anchor = own[0] if own else None
        moved = [a for _, a in found]
        while anchor is not None and anchor in moved:                 # the slot after an entry that moves away
            nxt = acts.index(anchor) + 1
            anchor = acts[nxt] if nxt < len(acts) else None
        if anchor is not None:
            target.insertMenu(anchor, sub)
        else:
            target.addMenu(sub)
        for menu, action in found:
            menu.removeAction(action)
            sub.addAction(action)
        for menu in {id(m): m for m, _ in found}.values():
            _tidy_separators(menu)
        _tidy_separators(target)
        made[title.replace("&", "")] = sub
    return made
