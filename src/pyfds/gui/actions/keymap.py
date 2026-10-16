"""Keyboard shortcut customisation (UI-21): every menu action can be given another key, with conflicts caught.

Actions are found by walking the menu bar, so the editor covers registry-built menus and plain ones alike. An
action's id is its menu path (``"View/Reset View"``); the user's changes are kept as ``{id: key}`` overrides
(an empty key means "no shortcut"), which is what gets saved between sessions.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtGui import QAction, QKeySequence


def _clean(text: str) -> str:
    return text.replace("&", "").strip()


def collect(menu_bar: Any) -> List[Tuple[str, QAction]]:
    """(id, action) for every leaf action under the menu bar, in menu order. Duplicated paths get ``#2``, ``#3``."""
    found: List[Tuple[str, QAction]] = []
    seen: Dict[str, int] = {}

    def walk(menu, path):
        for a in menu.actions():
            if a.isSeparator() or not _clean(a.text()):
                continue
            if a.menu() is not None:
                walk(a.menu(), path + [_clean(a.text())])
                continue
            base = "/".join(path + [_clean(a.text())])
            seen[base] = seen.get(base, 0) + 1
            found.append((base if seen[base] == 1 else f"{base}#{seen[base]}", a))

    for top in menu_bar.actions():
        if top.menu() is not None:
            walk(top.menu(), [_clean(top.text())])
    return found


def normalise(text: str) -> str:
    """The portable text of a key sequence (``ctrl+z`` -> ``Ctrl+Z``); ``""`` for none. Raises for nonsense."""
    text = (text or "").strip()
    if not text:
        return ""
    seq = QKeySequence(text, QKeySequence.PortableText)
    if seq.count() != 1 or not seq.toString(QKeySequence.PortableText):          # unparsable text comes back empty
        raise ValueError(f"{text!r} is not a key combination")
    return seq.toString(QKeySequence.PortableText)


class Keymap:
    """The shortcuts of one menu bar. Build it after the menus exist; defaults are what it finds at that moment."""

    def __init__(self, menu_bar: Any) -> None:
        self._actions = dict(collect(menu_bar))
        self._default = {i: a.shortcut().toString(QKeySequence.PortableText) for i, a in self._actions.items()}

    # -- reading ----------------------------------------------------------------------
    def ids(self) -> List[str]:
        return list(self._actions)

    def rows(self) -> List[Dict[str, str]]:
        return [{"id": i, "label": i.replace("/", " > "), "key": self.key(i), "default": self._default[i]}
                for i in self._actions]

    def key(self, action_id: str) -> str:
        return self._actions[self._known(action_id)].shortcut().toString(QKeySequence.PortableText)

    def default(self, action_id: str) -> str:
        return self._default[self._known(action_id)]

    def _known(self, action_id: str) -> str:
        if action_id not in self._actions:
            raise KeyError(f"no menu action {action_id!r}")
        return action_id

    def conflicts(self, text: str, exclude: Optional[str] = None) -> List[str]:
        """Ids of the other actions that already use this key (two actions on one key would stop both working)."""
        key = normalise(text)
        return [] if not key else [i for i in self._actions if i != exclude and self.key(i) == key]

    def overrides(self) -> Dict[str, str]:
        return {i: self.key(i) for i in self._actions if self.key(i) != self._default[i]}

    # -- changing ---------------------------------------------------------------------
    def set(self, action_id: str, text: str, steal: bool = False) -> List[str]:
        """Give an action a key (``""`` removes it). If another action has the key this raises ``ValueError`` -
        unless *steal*, which takes the key from it. Returns the ids that lost the key."""
        self._known(action_id)
        key = normalise(text)
        clash = self.conflicts(key, exclude=action_id)
        if clash and not steal:
            raise ValueError(f"{key} is already used by {', '.join(c.replace('/', ' > ') for c in clash)}")
        for c in clash:
            self._actions[c].setShortcut(QKeySequence())
        self._actions[action_id].setShortcut(QKeySequence(key, QKeySequence.PortableText))
        return clash

    def reset(self, action_id: str) -> None:
        self._actions[self._known(action_id)].setShortcut(QKeySequence(self._default[action_id], QKeySequence.PortableText))

    def reset_all(self) -> None:
        for i in self._actions:
            self.reset(i)

    # -- saving -----------------------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(self.overrides(), indent=2, sort_keys=True)

    def apply_json(self, text: str) -> int:
        """Apply saved overrides (unknown ids are skipped: the menu may have changed). Returns how many applied.
        Everything not mentioned goes back to its default first, so the result is exactly what the text says."""
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        self.reset_all()
        applied = 0
        for i, key in data.items():
            if i in self._actions and isinstance(key, str):
                try:
                    self.set(i, key, steal=True)
                    applied += 1
                except ValueError:
                    continue
        return applied
