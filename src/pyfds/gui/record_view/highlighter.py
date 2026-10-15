"""FDS syntax colours for the Record View."""
from __future__ import annotations

import re
from typing import List, Tuple

from PySide6.QtGui import QColor, QFont, QPalette, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QApplication

_LIGHT = {"tag": "#0b5394", "key": "#9a4d00", "string": "#1b7a3a", "number": "#7a2fb5", "logical": "#00798c",
          "end": "#888888", "free": "#888888"}
_DARK = {"tag": "#6fb1ff", "key": "#e0a458", "string": "#7fd18b", "number": "#c39bff", "logical": "#5fd4e6",
         "end": "#8a8a8a", "free": "#8a8a8a"}


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Bold)
    f.setFontItalic(italic)
    return f


def palette_for_app() -> dict:
    app = QApplication.instance()
    dark = app is not None and app.palette().color(QPalette.Window).lightness() < 128
    return _DARK if dark else _LIGHT


class FdsHighlighter(QSyntaxHighlighter):
    """Colours namelist names, parameter names, strings, numbers and logicals; text outside records (which FDS
    ignores) is grey italics."""

    def __init__(self, document, colors: dict = None) -> None:
        super().__init__(document)
        self.set_colors(colors or palette_for_app())

    def set_colors(self, colors: dict) -> None:
        self._free = _fmt(colors["free"], italic=True)
        # later rules win where they overlap: strings and parameter names override digits inside them
        self._rules: List[Tuple[re.Pattern, QTextCharFormat]] = [
            (re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?"), _fmt(colors["number"])),
            (re.compile(r"\.(?:TRUE|FALSE|T|F)\.", re.IGNORECASE), _fmt(colors["logical"], bold=True)),
            (re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\([^)]*\))?(?=\s*=)"), _fmt(colors["key"])),
            (re.compile(r"'[^']*'"), _fmt(colors["string"])),
            (re.compile(r"/\s*$"), _fmt(colors["end"])),
            (re.compile(r"^\s*&\w+"), _fmt(colors["tag"], bold=True)),
        ]
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:              # noqa: N802 (Qt API)
        if text.strip() and not text.lstrip().startswith("&"):
            self.setFormat(0, len(text), self._free)
            return
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
