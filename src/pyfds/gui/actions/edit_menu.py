"""The Edit menu as data."""
from __future__ import annotations

from PySide6.QtGui import QKeySequence

from .spec import SEPARATOR, ActionSpec

A = ActionSpec
K = QKeySequence

EDIT_MENU = [
    A("edit.undo", "&Undo", lambda w: w.api.history.undo, attr="_undo_action"),
    A("edit.redo", "&Redo", lambda w: w.api.history.redo, attr="_redo_action"),
    A("edit.undo_view", "Undo &View Change", "_on_undo_view", "Ctrl+Shift+Z"),
    A("edit.redo_view", "Redo View Chan&ge", "_on_redo_view", "Ctrl+Shift+Y"),
    SEPARATOR,
    A("edit.cut", "Cu&t", "_on_cut", K.Cut, attr="_cut_action"),
    A("edit.copy", "&Copy", "_on_copy", K.Copy, attr="_copy_action"),
    A("edit.paste", "&Paste", "_on_paste", K.Paste, attr="_paste_action", enabled=False),
    SEPARATOR,
    A("edit.delete", "&Delete Selected", "_on_delete_selected", K.Delete, attr="_delete_action"),
    A("edit.duplicate", "Dup&licate", "_on_duplicate", attr="_duplicate_action"),
    SEPARATOR,
    A("edit.properties", "Edit &Properties...", "_on_edit_properties"),
    SEPARATOR,
    A("edit.find", "&Find...", "_on_find", K.Find),
    A("edit.replace", "&Replace...", "_on_replace", K.Replace),
    SEPARATOR,
    A("edit.select_all", "Select &All", "_on_select_all", K.SelectAll),
    A("edit.hide", "&Hide Selected", "_on_hide_selected", "Alt+Shift+H"),
    A("edit.show", "Sho&w Selected", "_on_show_selected", "Alt+Shift+S"),
    A("edit.filter", "&Filter (Show Only Selection)", "_on_isolate_selected", "Alt+Shift+F"),
    A("edit.show_all", "Show A&ll", "_on_show_all", "Alt+Shift+A"),
    A("edit.group", "&Group Objects", "_on_group_selected"),
    A("edit.ungroup", "&Ungroup Objects", "_on_ungroup_selected"),
    SEPARATOR,
    A("edit.move", "&Move Selected...", "_on_move_selected"),
    A("edit.rotate", "&Rotate Selected...", "_on_rotate_selected"),
    A("edit.scale", "Sc&ale Selected...", "_on_scale_selected"),
    A("edit.mirror", "&Mirror Selected", "_on_mirror_selected"),
    A("edit.snap", "&Snap Settings...", "_on_snap_settings"),
]
