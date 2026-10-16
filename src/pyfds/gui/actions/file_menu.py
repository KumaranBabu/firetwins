"""The File menu as data."""
from __future__ import annotations

from .spec import SEPARATOR, ActionSpec, Submenu

A = ActionSpec

FILE_MENU = [
    A("file.new", "&New", "_on_new", attr="_new_action"),
    A("file.new_template", "New From &Template...", "_on_new_from_template"),
    A("file.open", "&Open...", "_on_open", attr="_open_action"),
    Submenu("file.recent", "&Recent", attr="_recent_submenu", on_built="_rebuild_recent_menu"),
    SEPARATOR,
    A("file.save", "&Save", "_on_save", attr="_save_action"),
    A("file.save_as", "&Save As...", "_on_save_as", attr="_save_as_action"),
    A("file.print", "&Print...", "_on_print"),
    SEPARATOR,
    A("file.preferences", "&Preferences...", "_on_preferences"),
    Submenu("file.import", "&Import", items=[
        A("file.import.fds", "Import FDS File...", "_on_import_fds"),
        A("file.import.stl", "Import Geometry (STL)...", "_on_import_stl"),
        A("file.import.materials", "Import Materials...", "_on_import_materials"),
        A("file.import.scenarios", "Import Scenarios...", "_on_import_scenarios"),
        A("file.import.devices", "Import Devices...", "_on_import_devices"),
        A("file.import.library", "Import from Library...", "_on_import_library"),
        A("file.import.config", "Import Configuration...", "_on_import_config"),
    ]),
    Submenu("file.export", "&Export", items=[
        A("file.export.fds", "Export as FDS...", "_on_export_as_fds"),
        A("file.export.stl", "Export Geometry (STL/OBJ)...", "_on_export_geometry"),
        A("file.export.scenarios", "Export Scenario Definitions...", "_on_export_scenario_definitions"),
        A("file.export.config", "Export Configuration...", "_on_export_config"),
    ]),
    SEPARATOR,
    A("file.project_settings", "Pro&ject Settings...", "_on_project_settings"),
    SEPARATOR,
    Submenu("file.export_db", "E&xport Database", items=[
        A("file.export_db.materials", "&Materials...", ("_on_export_db", "materials")),
        A("file.export_db.surfaces", "&Surfaces...", ("_on_export_db", "surfaces")),
        A("file.export_db.fuels", "&Fuels...", ("_on_export_db", "fuels")),
        A("file.export_db.all", "&All (folder)...", "_on_export_db_all"),
    ]),
    SEPARATOR,
    A("file.exit", "E&xit", "close"),
]
