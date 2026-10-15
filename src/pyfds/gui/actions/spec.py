"""Declarative menu actions (plan step G4).

A menu is described as data: ``ActionSpec`` items, ``Submenu`` groups and ``SEPARATOR``. ``ActionRegistry``
builds the Qt menu from that data, keeps every action by id (so toolbars, context menus and a command
palette can look the same action up instead of re-creating it) and sets ``owner.<attr>`` for the code that
still reaches actions by attribute.

``handler`` is one of: a method name on the owner (``"_on_new"``); a tuple ``("_on_export_db", "materials")``
(method name plus arguments); or a callable ``f(owner) -> callable`` for handlers that are not methods
(``lambda w: w.api.history.undo``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu


@dataclass(frozen=True)
class ActionSpec:
    id: str
    label: str
    handler: Union[str, tuple, Callable[[Any], Callable[[], None]], None] = None
    shortcut: Any = None            # a QKeySequence.StandardKey or a string such as "Ctrl+Shift+Z"
    attr: Optional[str] = None      # also stored as owner.<attr>
    enabled: bool = True
    checkable: bool = False
    checked: bool = False
    status_tip: str = ""
    placeholder: bool = False       # not implemented yet: its handler is a "Coming soon" box


@dataclass(frozen=True)
class Submenu:
    id: str
    label: str
    items: Sequence[Any] = ()
    attr: Optional[str] = None
    on_built: Optional[str] = None  # owner method called once the submenu exists (fills dynamic content)


SEPARATOR = None


def _resolve(owner: Any, handler: Any) -> Optional[Callable[[], None]]:
    if handler is None:
        return None
    if isinstance(handler, str):
        return getattr(owner, handler)
    if isinstance(handler, tuple):
        fn = getattr(owner, handler[0])
        args = handler[1:]
        return lambda checked=False: fn(*args)
    return handler(owner)


class ActionRegistry:
    def __init__(self) -> None:
        self._actions: Dict[str, QAction] = {}
        self._specs: Dict[str, ActionSpec] = {}
        self._menus: Dict[str, QMenu] = {}

    # -- building -------------------------------------------------------------------
    def build_menu(self, owner: Any, parent_menu_or_bar: Any, title: str, items: Sequence[Any],
                   menu_id: Optional[str] = None) -> QMenu:
        """Create a top-level menu (``parent_menu_or_bar`` is the menu bar) from *items*."""
        menu = parent_menu_or_bar.addMenu(title)
        if menu_id:
            self._menus[menu_id] = menu
        self._fill(owner, menu, items)
        return menu

    def _fill(self, owner: Any, menu: QMenu, items: Sequence[Any]) -> None:
        for item in items:
            if item is SEPARATOR:
                menu.addSeparator()
            elif isinstance(item, Submenu):
                sub = menu.addMenu(item.label)
                self._menus[item.id] = sub
                if item.attr:
                    setattr(owner, item.attr, sub)
                self._fill(owner, sub, item.items)
                if item.on_built:
                    getattr(owner, item.on_built)()
            else:
                self._add_action(owner, menu, item)

    def _add_action(self, owner: Any, menu: QMenu, spec: ActionSpec) -> QAction:
        if spec.id in self._actions:
            raise ValueError(f"duplicate action id {spec.id!r}")
        action = menu.addAction(spec.label)
        fn = _resolve(owner, spec.handler)
        if fn is not None:
            action.triggered.connect(fn)
        if spec.shortcut is not None:
            action.setShortcut(QKeySequence(spec.shortcut))
        if spec.checkable:
            action.setCheckable(True)
            action.setChecked(spec.checked)
        if spec.status_tip:
            action.setStatusTip(spec.status_tip)
        action.setEnabled(spec.enabled)
        if spec.attr:
            setattr(owner, spec.attr, action)
        self._actions[spec.id] = action
        self._specs[spec.id] = spec
        return action

    # -- lookup ---------------------------------------------------------------------
    def action(self, action_id: str) -> QAction:
        try:
            return self._actions[action_id]
        except KeyError:
            raise KeyError(f"no action {action_id!r}") from None

    def menu(self, menu_id: str) -> QMenu:
        return self._menus[menu_id]

    def spec(self, action_id: str) -> ActionSpec:
        return self._specs[action_id]

    def ids(self) -> List[str]:
        return list(self._actions)

    def set_enabled(self, action_id: str, enabled: bool) -> None:
        self.action(action_id).setEnabled(bool(enabled))

    def search(self, text: str) -> List[str]:
        """Ids of the actions whose label contains *text* (case-insensitive, mnemonics ignored): the
        data a command palette needs."""
        t = text.lower().replace("&", "")
        return [i for i, s in self._specs.items() if t in s.label.lower().replace("&", "").replace("...", "")]

    def placeholders(self) -> List[str]:
        return [i for i, s in self._specs.items() if s.placeholder]
