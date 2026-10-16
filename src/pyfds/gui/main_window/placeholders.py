"""Menu entries that are not built yet: one table of messages, handlers made from it."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox


PLACEHOLDERS = {
    '_on_placeholder_print': (
        'Coming Soon',
        'Print functionality will be available in Phase 3.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_import_fds': (
        'Coming Soon',
        'FDS file import will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_import_materials': (
        'Coming Soon',
        'Materials import will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_import_scenarios': (
        'Coming Soon',
        'Scenario import will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_import_devices': (
        'Coming Soon',
        'Device import will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_import_library': (
        'Coming Soon',
        'Library import will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_export_stl': (
        'Coming Soon',
        'STL export will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_export_config': (
        'Coming Soon',
        'Configuration export will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_toggle_grid': (
        'Coming Soon',
        'Grid toggle will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_toggle_axes': (
        'Coming Soon',
        'Axes toggle will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_split_horizontal': (
        'Coming Soon',
        'View splitting will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_split_vertical': (
        'Coming Soon',
        'View splitting will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_split_four_way': (
        'Coming Soon',
        'View splitting will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_add_control': (
        'Coming Soon',
        'Control elements will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_add_prop': (
        'Coming Soon',
        'Property elements will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_add_species': (
        'Coming Soon',
        'Species configuration will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_geometry_repair': (
        'Coming Soon',
        'Geometry repair will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_device_labels': (
        'Coming Soon',
        'Device labels will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_import_scenarios_dialog': (
        'Coming Soon',
        'Scenario import will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_gpu_settings': (
        'Coming Soon',
        'GPU settings will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_monitor_simulation': (
        'Coming Soon',
        'Simulation monitoring will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_tools_geometry_repair': (
        'Coming Soon',
        'Geometry repair will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_script_console': (
        'Coming Soon',
        'Script console will be available in Phase 3.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_examples': (
        'Coming Soon',
        'Examples browser will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_tutorials': (
        'Coming Soon',
        'Tutorials will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_check_updates': (
        'Coming Soon',
        'Update checker will be available in Phase 2.\n\nThis is a placeholder.',
    ),
}


class PlaceholderMixin:
    """"Coming Soon" handlers for menu entries whose backend is not built yet (one table, one factory)."""
    def _on_placeholder_geometry_primitive(self, shape_name: str) -> None:
        QMessageBox.information(
            self,
            "Coming Soon",
            f"Draw {shape_name} has no geometry backend yet — this is a placeholder."
        )

def _make_handler(title: str, text: str):
    def handler(self) -> None:
        QMessageBox.information(self, title, text)
    return handler


for _name, (_title, _text) in PLACEHOLDERS.items():
    _fn = _make_handler(_title, _text)
    _fn.__name__ = _name
    setattr(PlaceholderMixin, _name, _fn)
