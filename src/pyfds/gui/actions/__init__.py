"""Declarative menu definitions and the action registry (plan step G4)."""
from .edit_menu import EDIT_MENU
from .editor_menu import EDITABLE, EDITOR_MENU, EDITORS
from .file_menu import FILE_MENU
from .spec import SEPARATOR, ActionRegistry, ActionSpec, Submenu

__all__ = ["ActionRegistry", "ActionSpec", "Submenu", "SEPARATOR", "FILE_MENU", "EDIT_MENU", "EDITOR_MENU", "EDITORS", "EDITABLE"]
