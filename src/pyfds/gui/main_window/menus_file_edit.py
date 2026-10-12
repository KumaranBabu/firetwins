"""Menu construction: file, edit."""
from __future__ import annotations

from PySide6.QtGui import QKeySequence


class MenusFileEditMixin:
    def _build_file_menu(self) -> None:
        # Actions stashed on self.* are reused in the toolbar — checkable state
        # (e.g. Wireframe) stays in sync between menu and toolbar automatically.

        # ════════════════════════════════════════════════════════════════════════
        # FILE MENU (17 items)
        # ════════════════════════════════════════════════════════════════════════
        file_menu = self.menuBar().addMenu("&File")

        # Project lifecycle
        self._new_action = file_menu.addAction("&New", self._on_new)
        file_menu.addAction("New From &Template...", self._on_new_from_template)

        # Open / Recent
        self._open_action = file_menu.addAction("&Open...", self._on_open)
        self._recent_submenu = file_menu.addMenu("&Recent")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        # Save operations
        self._save_action = file_menu.addAction("&Save", self._on_save)
        self._save_as_action = file_menu.addAction("&Save As...", self._on_save_as)

        # Print (new)
        file_menu.addAction("&Print...", self._on_placeholder_print)

        file_menu.addSeparator()

        # Preferences (new)
        file_menu.addAction("&Preferences...", self._on_preferences)

        # Import submenu (new) - 6 items
        import_submenu = file_menu.addMenu("&Import")
        import_submenu.addAction("Import FDS File...", self._on_placeholder_import_fds)
        import_submenu.addAction("Import Geometry (STL)...", self._on_import_stl)
        import_submenu.addAction("Import Materials...", self._on_placeholder_import_materials)
        import_submenu.addAction("Import Scenarios...", self._on_placeholder_import_scenarios)
        import_submenu.addAction("Import Devices...", self._on_placeholder_import_devices)
        import_submenu.addAction("Import from Library...", self._on_placeholder_import_library)

        # Export submenu (new)
        export_submenu = file_menu.addMenu("&Export")
        export_submenu.addAction("Export as FDS...", self._on_export_as_fds)
        export_submenu.addAction("Export Geometry (STL)...", self._on_placeholder_export_stl)
        export_submenu.addAction("Export Configuration...", self._on_placeholder_export_config)

        file_menu.addSeparator()

        # Project Settings (new)
        file_menu.addAction("Pro&ject Settings...", self._on_project_settings)

        file_menu.addSeparator()

        # Export Database (existing, kept)
        export_db_menu = file_menu.addMenu("E&xport Database")
        export_db_menu.addAction("&Materials...", lambda: self._on_export_db("materials"))
        export_db_menu.addAction("&Surfaces...", lambda: self._on_export_db("surfaces"))
        export_db_menu.addAction("&Fuels...", lambda: self._on_export_db("fuels"))
        export_db_menu.addAction("&All (folder)...", self._on_export_db_all)

        file_menu.addSeparator()

        # Exit
        file_menu.addAction("E&xit", self.close)


    def _build_edit_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # EDIT MENU (18 items)
        # ════════════════════════════════════════════════════════════════════════
        edit_menu = self.menuBar().addMenu("&Edit")

        # Undo/Redo
        self._undo_action = edit_menu.addAction("&Undo", self.api.history.undo)
        self._redo_action = edit_menu.addAction("&Redo", self.api.history.redo)

        edit_menu.addSeparator()

        # Clipboard operations (new)
        self._cut_action = edit_menu.addAction("Cu&t", self._on_cut)
        self._cut_action.setShortcut(QKeySequence.Cut)
        self._copy_action = edit_menu.addAction("&Copy", self._on_copy)
        self._copy_action.setShortcut(QKeySequence.Copy)
        self._paste_action = edit_menu.addAction("&Paste", self._on_paste)
        self._paste_action.setShortcut(QKeySequence.Paste)
        self._paste_action.setEnabled(False)

        edit_menu.addSeparator()

        # Delete / Duplicate
        self._delete_action = edit_menu.addAction("&Delete Selected", self._on_delete_selected)
        self._delete_action.setShortcut(QKeySequence.Delete)
        self._duplicate_action = edit_menu.addAction("Dup&licate", self._on_duplicate)

        edit_menu.addSeparator()

        # Properties
        edit_menu.addAction("Edit &Properties...", self._on_edit_properties)

        edit_menu.addSeparator()

        # Find / Replace
        find_action = edit_menu.addAction("&Find...", self._on_find)
        find_action.setShortcut(QKeySequence.Find)
        replace_action = edit_menu.addAction("&Replace...", self._on_placeholder_replace)
        replace_action.setShortcut(QKeySequence.Replace)

        edit_menu.addSeparator()

        # Selection / Organization (new)
        edit_menu.addAction("Select &All", self._on_placeholder_select_all)
        edit_menu.addAction("&Filter...", self._on_placeholder_filter)
        edit_menu.addAction("&Group Objects", self._on_group_selected)
        edit_menu.addAction("&Ungroup Objects", self._on_ungroup_selected)

        edit_menu.addSeparator()

        # Transform operations (new) — placeholder until 3D viewport supports
        edit_menu.addAction("&Move Selected...", self._on_move_selected)
        edit_menu.addAction("&Rotate Selected...", self._on_rotate_selected)
        edit_menu.addAction("Sc&ale Selected...", self._on_scale_selected)
        edit_menu.addAction("&Mirror Selected", self._on_mirror_selected)
        edit_menu.addAction("&Snap Settings...", self._on_snap_settings)
