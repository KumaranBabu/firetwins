"""Menu entries that are not built yet: one table of messages, handlers made from it."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox


PLACEHOLDERS = {
    '_on_placeholder_print': (
        'Coming Soon',
        'Print functionality will be available in Phase 3.\n\nThis is a placeholder.',
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
    '_on_placeholder_gpu_settings': (
        'Coming Soon',
        'GPU settings will be available in Phase 2.\n\nThis is a placeholder.',
    ),
    '_on_placeholder_script_console': (
        'Coming Soon',
        'Script console will be available in Phase 3.\n\nThis is a placeholder.',
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
    pass


def _make_handler(title: str, text: str):
    def handler(self) -> None:
        QMessageBox.information(self, title, text)
    return handler


for _name, (_title, _text) in PLACEHOLDERS.items():
    _fn = _make_handler(_title, _text)
    _fn.__name__ = _name
    setattr(PlaceholderMixin, _name, _fn)
