"""Menu entries that are not built yet: one table of messages, handlers made from it."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox


PLACEHOLDERS = {
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
